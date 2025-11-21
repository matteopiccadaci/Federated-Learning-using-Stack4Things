import asyncio
import torch
import socket
import threading
import io
from oslo_log import log as logging
import json
import base64
import torch.nn as nn
import torch.nn.functional as F
from iotronic_lightningrod.modules.plugins import Plugin
#from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import ssl
from autobahn.asyncio.component import Component
from torchvision import datasets, transforms
import torch.utils.data as data_utils


LOG = logging.getLogger(__name__)
board_name = socket.gethostname()
workers = set()


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

    def fedavg(self, state_dicts, ns):
        """Media pesata dei pesi: w = somma_i (n_i / N) * w_i"""
        assert len(state_dicts) == len(ns)
        N = float(sum(ns))

        # inizializza con una copia del primo
        avg_state = {k: v.clone() for k, v in state_dicts[0].items()}

        for key in avg_state.keys():
            avg_state[key].zero_()
            for state, n_i in zip(state_dicts, ns):
                avg_state[key] += (n_i / N) * state[key]

            return avg_state

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
                    LOG.info("[WAMP] RPCs registered: train_round")

                    async def notify_join(*args, **kwargs):
                        wrk=json.loads(base64.b64decode(args[0])["board"])
                        workers.add(wrk)
                        LOG.info(f"[WAMP] Added new worker: {wrk}")
                        return f"Hello {wrk}, you correctly joined!"
                    
                    async def notify_leave(*args, **kwargs):
                        wrk=json.loads(base64.b64decode(args[0])["board"])
                        workers.remove(wrk)
                        LOG.info(f"[WAMP] Removed worker: {wrk}")
                        return f"Goodbye {wrk}, you correctly left!"

                    async def federated_loop(self):
                        # inizializza modello globale
                        global_model = Net()
                        num_rounds   = 3

                        for rnd in range(num_rounds):
                            print(f"\n=== ROUND {rnd} ===")

                            # 1) serializza i pesi globali
                            global_bytes = self.model_to_bytes(global_model)

                            # 2) chiama in parallelo i worker
                            calls = []
                            for wrk in workers:
                                uri = f"iotronic.{wrk}.train_round"
                                calls.append(self.call(uri, global_bytes))

                            # aspetta le risposte: [(bytes1, n1), (bytes2, n2), ...]
                            results = await asyncio.gather(*calls)
                            print(results)

                            # 3) aggrega (FedAvg sui pesi)
                            state_dicts = []
                            ns          = []
                            for (updated_model, n_i) in results:
                                tmp_model = Net()
                                self.bytes_to_model(tmp_model, updated_model)
                                state_dicts.append(tmp_model.state_dict())
                                ns.append(n_i)

                            # FedAvg
                            new_state_dict = self.fedavg(state_dicts, ns)
                            global_model.load_state_dict(new_state_dict)

                            print(f"Round {rnd} completed, global model updated.")

                        print("Federated training finished.")
                        await self.leave()
                
                    await session.register(federated_loop, f"iotronic.{board_name}.federated_loop")
                    await session.register(notify_join, f"iotronic.{board_name}.notify_join")
                    await session.register(notify_leave, f"iotronic.{board_name}.notify_leave")
                await component.start()
            while True:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(wamp_main())
                except Exception as e:
                    LOG.error(f"[WAMP] Error in WAMP loop: {e}")
                finally:
                    asyncio.set_event_loop(None)


        threading.Thread(target=start_wamp, name="WAMP_FLMaster", daemon=True).start()
        LOG.info("[WAMP] Master set, waiting for RPC...")