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
from ssl import _create_unverified_context
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Util.number import long_to_bytes, bytes_to_long
import string
import random

train_dataset = None
train_loader = None
LOG = logging.getLogger(__name__)
board_name = socket.gethostname()
local_epochs = 5
master_name = "LR_Master"

with open(f"/etc/ssl/iotronic/node_certs/{board_name}.key.pem", "rb") as f:
    priv_K_wrk = RSA.import_key(f.read())
with open(f"/etc/ssl/iotronic/node_certs/{master_name}.pub.pem", "rb") as f:
    pub_K_master = RSA.import_key(f.read())

# RSA signature generation routine, since the library does not provide it nativel
message = board_name.encode()
m_int = bytes_to_long(message)
signature_int = pow(m_int, priv_K_wrk.d, priv_K_wrk.n)
signature = long_to_bytes(signature_int)

# RSA signature validation routine, since the library does not provide it natively
def validate_signature(signature, original_msg):
    sig_int = bytes_to_long(signature)
    m_check_int = pow(sig_int, pub_K_master.e, pub_K_master.n)
    m_check = long_to_bytes(m_check_int)
    return m_check == original_msg.encode()

def random_key():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))

def decrypt_model(encr_model, encr_key):
    # Decrypt AES key with RSA
    cipher_rsa = PKCS1_v1_5.new(priv_K_wrk)
    aes_key = cipher_rsa.decrypt(encr_key, None).decode('utf-8')

    # Decrypt model with AES
    cipher_aes = AES.new(aes_key.encode('utf-8'), AES.MODE_ECB)
    decrypted_model = unpad(cipher_aes.decrypt(encr_model), AES.block_size)

    return decrypted_model

def encrypt_updated_model(model_bytes, n_samples, aes_key):
    # Encrypt model with AES
    cipher_aes = AES.new(aes_key.encode('utf-8'), AES.MODE_ECB)
    padded_model = pad(model_bytes, AES.block_size)
    encr_model = cipher_aes.encrypt(padded_model)
    encr_n_samples = cipher_aes.encrypt(pad(str(n_samples).encode('utf-8'), AES.block_size))

    # Encrypt AES key with RSA
    cipher_rsa = PKCS1_v1_5.new(pub_K_master)
    encr_key = cipher_rsa.encrypt(aes_key.encode('utf-8'))

    return encr_model, encr_n_samples, encr_key


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

def training(b_model):
    device = torch.device("cpu")

    model = Net().to(device)
    bytes_to_model(model, b_model)

    optimizer = optim.SGD(model.parameters(), lr=0.01)

    LOG.info(f"[{board_name}] Training started")
    model.train()
    for epoch in range(local_epochs):
        LOG.info(f"[{board_name}] Starting epoch:{epoch + 1} of {local_epochs}")
        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.nll_loss(output, target)
            loss.backward()
            optimizer.step()

    LOG.info(f"[{board_name}] Training ended")
    updated_bytes_model = model_to_bytes(model)
    n_samples = len(train_dataset)

    return updated_bytes_model, n_samples

class Worker(Plugin.Plugin):
    def __init__(self, uuid, name, q_result=None, params=None):
        super(Worker, self).__init__(uuid, name, q_result, params)

    def run(self):
        shard_path = "/opt/mnist/mnist_shard.pt"

        load_local_dataset(shard_path)
        LOG.info(f"[{board_name}] Local dataset loaded from {shard_path} "
                 f"({len(train_dataset)} samples)")
        uri = f"iotronic.{master_name}.notify_join"
        
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
                    await session.call(uri, {"board": board_name, "signature": signature})
                    LOG.info(f"[WAMP] Session joined as {board_name}")
                    LOG.info("[WAMP] RPCs registered: set_dataset, train_round, leave_session, stop_training, start_training")
                    session.stop_training=False

                    async def leave_session(*args, **kwargs):
                        await session.call(f"iotronic.{master_name}.notify_leave", json.dumps({"board": board_name}))
                        LOG.info(f"[WAMP] Session left")
                    
                    async def stop_training(*args, **kwargs):
                        if validate_signature(args[0]['signature'], master_name):
                            session.stop_training=True
                            await session.call(uri, {"board": board_name, "signature": signature}) # The worker re-notifies its presence
                            LOG.info(f"[{board_name}] stop_training RPC called, stopping training after current round")
                        else:
                            session.stop_training=False
                            LOG.warning(f"[{board_name}] stop_training RPC called with invalid signature!")
                    
                    async def start_training(*args, **kwargs):
                        if validate_signature(args[0]['signature'], master_name):
                            session.stop_training=False
                            LOG.info(f"[{board_name}] start_training RPC called, starting training")
                        else:
                            session.stop_training=True
                            LOG.warning(f"[{board_name}] start_training RPC called with invalid signature!")

                    async def train_round (*args, **kwargs):
                        global train_loader, train_dataset

                        if train_loader is None or train_dataset is None:
                            LOG.error(f"[{board_name}] train_round called without a valid dataset!")

                        if not session.stop_training:
                            try:
                                b_model= decrypt_model(args[0]['encr_model'], args[0]['encr_key'])
                                loop = asyncio.get_running_loop()
                                updated_bytes_model, n_samples = await loop.run_in_executor(None, training, b_model)
                                '''
                                The usage of an asynchronous function is necessary in order to avoid an automatic timeout from Crossbar.
                                In order to avoid implementation problems, a new thread is spawned (for the same reason start_wamp is handled by a thread)
                                '''
                                updated_encrypted_model, encr_n_samples, encr_key = encrypt_updated_model(updated_bytes_model, n_samples, random_key())

                                LOG.info(f"[{board_name}] training ended, n_samples={n_samples}")

                                return {"updated_model": updated_encrypted_model, "n_samples": encr_n_samples, "encr_key": encr_key}
                            except Exception as e:
                                LOG.error(f"[{board_name}] Error during training: {e}")
                                pass

                                    
                    await session.register(leave_session, f"iotronic.{board_name}.leave_session")
                    await session.register(stop_training, f"iotronic.{board_name}.stop_training")
                    await session.register(start_training, f"iotronic.{board_name}.start_training")
                    await session.register(train_round, f"iotronic.{board_name}.train_round")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    component.start(loop=loop)
                    loop.run_forever()
                except Exception as e:
                    LOG.error(f"[WAMP] Error in WAMP loop: {e}")

        threading.Thread(target=start_wamp, name="WAMP_Secure_FLWorker", daemon=True).start()
        LOG.info("[WAMP] Worker set, waiting for RPC...")
        self.q_result.put("WAMP_Secure_FLWorker plugin correctly started") # Used to notify the correct start of the plugin to S4T
