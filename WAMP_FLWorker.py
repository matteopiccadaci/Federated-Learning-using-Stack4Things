import asyncio
import json
import socket
import ssl
import torch
import io
import base64
import threading
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from oslo_log import log as logging
from iotronic_lightningrod.modules.plugins import Plugin
from autobahn.asyncio.component import Component
from torchvision import datasets, transforms
from torch.utils.data import TensorDataset, DataLoader

train_dataset = None
train_loader = None
LOG = logging.getLogger(__name__)
board_name = socket.gethostname()
local_epochs = 5

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 20, 5, 1)
        self.conv2 = nn.Conv2d(20, 50, 5, 1)
        self.fc1   = nn.Linear(4*4*50, 500)
        self.fc2   = nn.Linear(500, 10)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.max_pool2d(x, 2, 2)
        x = F.relu(self.conv2(x))
        x = F.max_pool2d(x, 2, 2)
        x = x.view(-1, 4*4*50)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


class Worker(Plugin.Plugin):
    def __init__(self, uuid, name, q_result=None, params=None):
        super(Worker, self).__init__(uuid, name, q_result, params)

    def load_local_dataset(shard_path):
        global train_dataset, train_loader

        data_tensor, target_tensor = torch.load(shard_path, map_location="cpu")

        train_dataset = TensorDataset(data_tensor, target_tensor)
        train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

    def bytes_to_model(model, model_bytes: bytes):
        buffer = io.BytesIO(model_bytes)
        state_dict = torch.load(buffer, map_location="cpu")
        model.load_state_dict(state_dict)
        return model
    
    def model_to_bytes(model):
        buffer = io.BytesIO()
        torch.save(model.state_dict(), buffer)
        return buffer.getvalue()

    def run(self):
        shard_path = self.config.extra.get(
            "dataset_shard",
            "/opt/mnist/mnist_shard_0.pt"  # default di emergenza
        )

        self.load_local_dataset(shard_path)
        LOG.info(f"[{board_name}] Dataset locale caricato da {shard_path} "
                 f"({len(train_dataset)} campioni)")
        uri = f"iotronic.LR_Master.notify_join"
        self.call(uri, json.dumps({"board": board_name}))
        def start_wamp():
            async def wamp_main():
                ssl_ctx = ssl._create_unverified_context()

                component = Component(
                    transports=[
                        {
                            "type": "websocket",
                            "url": "wss://crossbar:8181/ws",
                            "endpoint": {
                                "type": "tcp",
                                "host": "crossbar",
                                "port": 8181,
                                "tls": ssl_ctx
                            },
                            "serializers": ["json", "msgpack"]
                        }
                    ],
                    realm="s4t"
                )
            
                @component.on_join
                async def onJoin(session, details):
                    LOG.info(f"[WAMP] Session joined as {board_name}")
                    LOG.info("[WAMP] RPCs registered: set_dataset, train_round")

                    async def train_round(self, *args, **kwargs):
                        """
                        RPC chiamata dal server:
                        - riceve modello globale in bytes
                        - fa qualche epoca di training locale
                        - restituisce modello aggiornato + numero campioni
                        """
                        global train_loader, train_dataset

                        if train_loader is None or train_dataset is None:
                            LOG.error(f"[{board_name}] train_round called without a valid dataset!")
                    
                        b_model= json.loads(base64.b64decode(args[0])["model"])
                        device = torch.device("cpu")

                        model = Net().to(device)
                        self.bytes_to_model(model, b_model)

                        optimizer = optim.SGD(model.parameters(), lr=0.01)

                        model.train()
                        for epoch in range(local_epochs):
                            for batch_idx, (data, target) in enumerate(train_loader):
                                data, target = data.to(device), target.to(device)
                                optimizer.zero_grad()
                                output = model(data)
                                loss = F.nll_loss(output, target)
                                loss.backward()
                                optimizer.step()

                        updated_bytes_model = Worker.model_to_bytes(model)
                        updated_bytes_model_b64 = base64.b64encode(updated_bytes_model).decode("ascii")
                        n_samples = len(train_dataset)

                        LOG.info(f"[{board_name}] training ended, n_samples={n_samples}")

                        return {"updated_model": updated_bytes_model_b64, "n_samples": n_samples}

                                    
                
                    await session.register(train_round, f"iotronic.{board_name}.train_round")
                await component.start()
            while True:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(wamp_main())
                except Exception as e:
                    LOG.error(f"[WAMP] Error in WAMP loop: {e}")
                    uri = f"iotronic.LR_Master.notify_leave"
                    self.call(uri, json.dumps({"board": board_name}))
                finally:
                    asyncio.set_event_loop(None)
                    uri = f"iotronic.LR_Master.notify_leave"
                    self.call(uri, json.dumps({"board": board_name}))

        threading.Thread(target=start_wamp, name="WAMP_FLWorker", daemon=True).start()
        LOG.info("[WAMP] Worker set, waiting for RPC...")
