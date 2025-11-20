import asyncio
from fastapi import FastAPI, HTTPException
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from ssl import _create_unverified_context
from typing import Optional
import threading
import uvicorn
import json


app = FastAPI()
wamp_session: Optional[ApplicationSession] = None

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
    # Avvia WAMP client come task asincrono all'avvio di FastAPI
    asyncio.create_task(start_wamp())

@app.get("/")
def get_boards():
    return {
        "boards": "Board_2_SRV, Board_3_SRV, Board_4_SRV",
        "_links": {
            "self": {"href": f"/iotronic/boards/"},
            "Board_2_SRV": {"href": f"/iotronic/boards/Board_2_SRV"},
            "Board_3_SRV": {"href": f"/iotronic/boards/Board_3_SRV"},
            "Board_4_SRV": {"href": f"/iotronic/boards/Board_4_SRV"}
        }
    }

# Board_2_SRV

@app.get("/iotronic/boards/Board_2_SRV")
def board_2_srv_get_RPCs():
    return {
        "board": "Board_2_SRV",
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_2_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_2_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/secure_write_to_db" }
        }
    }

@app.get("/iotronic/boards/Board_2_SRV/get_data")
async def board_2_srv_get_data():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_2_SRV.get_data")
        return {
        "board": "Board_2_SRV",
        "data": result,
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_2_SRV" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/secure_write_to_db" }
        }
    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/iotronic/boards/Board_2_SRV/clear_write_to_db")
async def board_2_srv_clear_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_2_SRV.clear_write_to_db")
        print (result)
        print(type(result))
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_2_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_2_SRV/get_data" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/secure_write_to_db" }
        }
    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/iotronic/boards/Board_2_SRV/secure_write_to_db")
async def board_2_srv_secure_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_2_SRV.secure_write_to_db")
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_2_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_2_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_2_SRV/clear_write_to_db" },
        }
    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Board_3_SRV

@app.get("/iotronic/boards/Board_3_SRV")
def board_3_srv_get_RPCs():
    return {
        "board": "Board_3_SRV",
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_3_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_3_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/secure_write_to_db" }
        }
    }

@app.get("/iotronic/boards/Board_3_SRV/get_data")
async def board_3_srv_get_data():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_3_SRV.get_data")
        return  {
        "board": "Board_3_SRV",
        "data": result,
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_3_SRV" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/secure_write_to_db" }
        }
    }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/iotronic/boards/Board_3_SRV/clear_write_to_db")
async def board_3_srv_clear_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_3_SRV.clear_write_to_db")
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_3_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_3_SRV/get_data" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/secure_write_to_db" }
        }
    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/iotronic/boards/Board_3_SRV/secure_write_to_db")
async def board_3_srv_secure_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_3_SRV.secure_write_to_db")
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_3_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_3_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_3_SRV/clear_write_to_db" }
        }
    }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Board_4_SRV

@app.get("/iotronic/boards/Board_4_SRV")
def board_4_srv_get_RPCs():
    return {
        "board": "Board_4_SRV",
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_4_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_4_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/secure_write_to_db" }
        }
    }

@app.get("/iotronic/boards/Board_4_SRV/get_data")
async def board_4_srv_get_data():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_4_SRV.get_data")
        return {
        "board": "Board_4_SRV",
        "data": result,
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_4_SRV" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/clear_write_to_db" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/secure_write_to_db" }
        }
    }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/iotronic/boards/Board_4_SRV/clear_write_to_db")
async def board_4_srv_clear_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_4_SRV.clear_write_to_db")
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_4_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_4_SRV/get_data" },
            "secure_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/secure_write_to_db" }
        }
    }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/iotronic/boards/Board_4_SRV/secure_write_to_db")
async def board_4_srv_secure_write_to_db():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    try:
        result = await wamp_session.call("iotronic.Board_4_SRV.secure_write_to_db")
        result = json.loads(result)
        return {
        "board": result['1'],
        "data": result['0'],
        "_links": {
            "self": { "href": f"/iotronic/boards/Board_4_SRV" },
            "get_data": { "href": f"/iotronic/boards/Board_4_SRV/get_data" },
            "clear_write_to_db": { "href": f"/iotronic/boards/Board_4_SRV/clear_write_to_db" }
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