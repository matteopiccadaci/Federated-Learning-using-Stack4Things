import asyncio
from fastapi import FastAPI, HTTPException
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from ssl import _create_unverified_context
from typing import Optional
import threading
import uvicorn
import json

# At the invocation of the app an error regarding the threading loop will appear, but it can be ignored

app = FastAPI()
wamp_session: Optional[ApplicationSession] = None
master_hostname = "LR_Master"


class WAMPClient(ApplicationSession):
    async def onJoin(self, details):
        global wamp_session
        wamp_session = self
        print("[WAMP] Sessione connessa")


async def start_wamp():
    ssl_context = _create_unverified_context()

    runner = ApplicationRunner(
        url="wss://crossbar:8181/ws",
        realm="s4t",
        ssl=ssl_context
    )

    await runner.run(WAMPClient, start_loop=False)


# Index
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_wamp())


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
            "self": {
                "href": f"/iotronic/boards/FL_master"
            },
            "federated_loop": {
                "href": f"/iotronic/boards/FL_master/federated_loop"
            }
        }
    }


@app.get("/iotronic/boards/FL_master/federated_loop")
async def FL_master_federated_loop():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call(f"iotronic.{master_hostname}.federated_loop")
        return {
            "board": "FL_master",
            "data": result,
            "_links": {
                "self": {
                    "href": f"/iotronic/boards/FL_master/federated_loop"
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def run_wamp():
    ssl_context = _create_unverified_context()
    runner = ApplicationRunner(
        url="wss://crossbar:8181/ws",
        realm="s4t",
        ssl=ssl_context
    )
    runner.run(WAMPClient)


if __name__ == "__main__":
    threading.Thread(target=run_wamp, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=4053)
