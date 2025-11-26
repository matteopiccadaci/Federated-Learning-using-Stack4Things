# app.py
import threading
from typing import Optional
from ssl import _create_unverified_context

from fastapi import FastAPI, HTTPException
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import uvicorn

app = FastAPI()
wamp_session: Optional[ApplicationSession] = None


class WAMPClient(ApplicationSession):
    async def onJoin(self, details):
        global wamp_session
        wamp_session = self
        print("[WAMP] Sessione connessa")

    async def onDisconnect(self):
        global wamp_session
        wamp_session = None
        print("[WAMP] Disconnesso")


def run_wamp():
    """
    Funzione bloccante: crea e avvia l'ApplicationRunner.
    Deve essere eseguita in un thread separato perché runner.run() blocca.
    """
    try:
        ssl_context = _create_unverified_context()  # mantiene il comportamento originale (non verificare cert)
        runner = ApplicationRunner(
            url="wss://crossbar:8181/ws",  # se Crossbar NON usa TLS, cambiare in "ws://crossbar:8181/ws"
            realm="s4t",
            ssl=ssl_context
        )
        print("[WAMP] Avvio runner WAMP (thread)...")
        runner.run(WAMPClient)  # blocca fino a terminazione del runner
        print("[WAMP] runner.run() terminato")
    except Exception as exc:
        # log semplice per eventuali errori nella connessione WAMP
        print(f"[WAMP] Errore nel run_wamp: {exc}")


# --- Startup: avviare run_wamp in un thread ---
@app.on_event("startup")
def startup_event():
    # Avvia il runner WAMP in un thread daemon in modo che non blocchi il processo principale.
    thread = threading.Thread(target=run_wamp, daemon=True)
    thread.start()
    print("[APP] Thread WAMP avviato nel startup")


# --- Routes HATEOAS ---
@app.get("/")
def get_boards():
    return {
        "boards": "FL_master",
        "_links": {
            "self": {"href": f"/iotronic/boards/"},
            "federated_loop": {"href": f"/iotronic/boards/FL_master"}
        }
    }


@app.get("/iotronic/boards/FL_master")
def FL_master_get_RPC():
    return {
        "board": "FL_master",
        "_links": {
            "self": {"href": f"/iotronic/boards/FL_master"},
            "federated_loop": {"href": f"/iotronic/boards/FL_master/federated_loop"}
        }
    }


@app.get("/iotronic/boards/FL_master/federated_loop")
async def FL_master_federated_loop():
    if not wamp_session:
        # WAMP non pronto: ritorniamo 503
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        # Esegui la RPC WAMP
        result = await wamp_session.call("iotronic.FL_master.federated_loop")
        return {
            "board": "FL_master",
            "data": result,
            "_links": {
                "self": {"href": f"/iotronic/boards/FL_master/federated_loop"}
            }
        }
    except Exception as e:
        # In caso di errore nella chiamata WAMP rispondiamo con 500
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Se lanci il file direttamente, uvicorn parte e lo startup_event avvierà il thread WAMP.
    uvicorn.run(app, host="0.0.0.0", port=4053)
