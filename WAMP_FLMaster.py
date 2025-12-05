import asyncio
import torch
import socket
import threading
import io
from oslo_log import log as logging
import json
import torch.nn as nn
import torch.nn.functional as F
from iotronic_lightningrod.modules.plugins import Plugin
#from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import ssl
from autobahn.asyncio.component import Component
from torchvision import datasets, transforms
import torch.utils.data as data_utils
import base64
import random
from torchvision import datasets, transforms
from PIL import Image
from pathlib import Path


LOG = logging.getLogger(__name__)
board_name = socket.gethostname()
LOG.info(f"[WAMP] Board name: {board_name}")
workers = set()

def bytes_to_model(model, model_bytes: bytes):
    buffer = io.BytesIO(model_bytes)
    state_dict = torch.load(buffer, map_location="cpu")
    model.load_state_dict(state_dict)
    return model
    
def model_to_bytes(model):
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return buffer.getvalue()

def fedavg(state_dicts, ns):
    assert len(state_dicts) == len(ns)
    N = float(sum(ns))

    # inizializza con una copia del primo
    avg_state = {k: v.clone() for k, v in state_dicts[0].items()}

    for key in avg_state.keys():
        avg_state[key].zero_()
        for state, n_i in zip(state_dicts, ns):
            avg_state[key] += (n_i / N) * state[key]
    return avg_state


def perform_inference_routine(model, image):
    model.load_state_dict(torch.load("/opt/models/global_model.pth", map_location="cpu"))
    model.eval()
    img = Image.open(io.BytesIO(image)).convert("L")

    transform = transforms.Compose([
        transforms.Resize((28, 28)),
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    x = transform(img).unsqueeze(0)
    with torch.no_grad():
        output = model(x) 
        pred_idx = int(output.argmax(dim=1).item())
        probs = torch.softmax(output, dim=1).squeeze(0).tolist()
        for i in range(len(probs)):
            probs[i] = round(probs[i],4)
    
    return {"predicted_index": pred_idx, "probabilities": probs}


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


    def run(self):
        def start_wamp():
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
                    LOG.info("[WAMP] RPCs registered: federated_loop, stop_training, notify_join, notify_leave, perform_inference")
                    session.stop_train=False
                    session.running=False
                    session.model_ready = Path("/opt/models/global_model.pth").exists() # True if the model already exists

                    async def notify_join(*args, **kwargs):
                        wrk=json.loads(args[0])["board"]
                        workers.add(wrk)
                        LOG.info(f"[WAMP] Added new worker: {wrk}")
                        return f"Hello {wrk}, you correctly joined!"
                    
                    async def notify_leave(*args, **kwargs):
                        wrk=json.loads(args[0])["board"]
                        workers.remove(wrk)
                        LOG.info(f"[WAMP] Removed worker: {wrk}")
                        return f"Goodbye {wrk}, you correctly left!"

                    async def federated_loop(*args, **kwargs):
                        session.running=True
                        session.stop_train=False
                        global_model = Net()
                        rnd=0
                        LOG.info(f"[WAMP] Federated learning loop started")
                        if len(workers) >= 1:
                                for wrk in workers:
                                    uri = f"iotronic.{wrk}.start_training"
                                    session.call(uri)

                        while not session.stop_train:
                            global_bytes = model_to_bytes(global_model)

                            calls = []
                            LOG.info(f"[WAMP] Current workers: {workers}")
                            if len(workers) >= 1:
                                for wrk in workers:
                                    uri = f"iotronic.{wrk}.train_round"
                                    calls.append(session.call(uri, global_bytes))
                                
                                try:
                                    results = await asyncio.gather(*calls)
                                    state_dicts = []
                                    ns          = []
                                    for result in results:
                                        tmp_model = Net()
                                        bytes_to_model(tmp_model, result['updated_model'])
                                        state_dicts.append(tmp_model.state_dict())
                                        ns.append(result["n_samples"])

                                        new_state_dict = fedavg(state_dicts, ns)
                                        global_model.load_state_dict(new_state_dict)

                                    LOG.info(f"[WAMP] Round {rnd+1} completed, global model updated.")
                                    rnd+=1
                                    if rnd % 5 ==0: # Save every 5 rounds
                                        save_path = "/opt/models/global_model.pth"
                                        torch.save(global_model.state_dict(), save_path)
                                        session.model_ready=True
                                        LOG.info(f"[WAMP] Global model saved to {save_path}")
                                    
                                except Exception as e:
                                    LOG.error(f"[WAMP] Error during federated learning round: {e}, notifying workers to stop training.")
                                    for wrk in list(workers):  # To avoid modification during iteration
                                        try:
                                            LOG.info(f"[WAMP] Notifying worker {wrk} to stop training.")
                                            await session.call(f"iotronic.{wrk}.stop_training")
                                        except Exception as notify_error:
                                            workers.discard(wrk)
                                            session.stop_train=True
                                            session.running=False
                                            return {"status": "error", "detail": "Error during federated learning round, please restart the training session."}
                                else:
                                        LOG.info("[WAMP] Not enough workers connected for federated learning.")
                                        session.stop_train=True
                                        session.running=False
                                        return {"status": "error", "detail": "Not enough workers connected for federated learning."}
                    
                    async def stop_training(*args, **kwargs):
                        session.stop_train=True
                        session.running=False
                        while session.running:
                            await asyncio.sleep(1)
                        for wrk in workers:
                            LOG.info(f"[WAMP] Notifying worker {wrk} to stop training.")
                            await session.call(f"iotronic.{wrk}.stop_training")
                        LOG.info("[WAMP] Federated learning loop stopped by master.")
                        return {"status": "success", "detail": "Federated learning loop stopped."}

                    async def perform_inference(*args, **kwargs):
                        if not session.model_ready:
                            return {"status": "error", "detail": "Model is not ready for inference."}
                        else: 
                            data=args[0]
                            image=base64.b64decode(data["image_base64"])
                            model = Net()
                            predictions = perform_inference_routine(model, image)
                            LOG.info(f"[WAMP] Inference performed, predicted index: {predictions['predicted_index']}")
                            return predictions              
                
                    await session.register(federated_loop, f"iotronic.{board_name}.federated_loop")
                    await session.register(stop_training, f"iotronic.{board_name}.stop_training")
                    await session.register(notify_join, f"iotronic.{board_name}.notify_join")
                    await session.register(notify_leave, f"iotronic.{board_name}.notify_leave")
                    await session.register(perform_inference, f"iotronic.{board_name}.perform_inference")

                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    component.start(loop=loop)
                    loop.run_forever()
                except Exception as e:
                    LOG.error(f"[WAMP] Error in WAMP loop: {e}")


        threading.Thread(target=start_wamp, name="WAMP_FLMaster", daemon=True).start()
        LOG.info("[WAMP] Master set, waiting for RPC...")
        self.q_result.put("WAMP_FLMaster plugin correctly started") # Used to notify the correct start of the plugin to S4T
