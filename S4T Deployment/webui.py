import asyncio
import base64
from ssl import _create_unverified_context
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner

app = FastAPI()
wamp_session: Optional[ApplicationSession] = None
master_hostname = "LR_Master"


class WAMPClient(ApplicationSession):
    async def onJoin(self, details):
        global wamp_session
        wamp_session = self
        print("[WAMP] Sessione connessa al router WAMP")


async def start_wamp():
    ssl_context = _create_unverified_context()

    runner = ApplicationRunner(
        url="wss://crossbar:8181/ws",
        realm="s4t",
        ssl=ssl_context
    )
    await runner.run(WAMPClient, start_loop=False)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_wamp())


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
            },
            "stop_training": {
                "href": f"/iotronic/boards/FL_master/stop_training"
            },
            "perform_inference": {
                "href": f"/iotronic/boards/FL_master/perform_inference"
            }
        }
    }


@app.get("/iotronic/boards/FL_master/federated_loop")
async def FL_master_federated_loop():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

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


@app.get("/iotronic/boards/FL_master/stop_training")
async def FL_master_stop_training():
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    result = await wamp_session.call(f"iotronic.{master_hostname}.stop_training")
    return {
        "board": "FL_master",
        "data": result,
        "_links": {
            "self": {
                "href": f"/iotronic/boards/FL_master/stop_training"
            }
        }
    }


# ===============================
#       UI WEB CON BOTTONI
# ===============================

@app.get("/", response_class=HTMLResponse)
async def ui_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8" />
        <title>FL Master - Inference & Control</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #111827;
                color: #e5e7eb;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start;
                min-height: 100vh;
                margin: 0;
                padding-top: 30px;
            }
            h1 {
                margin-bottom: 4px;
            }
            h2 {
                margin-top: 24px;
                margin-bottom: 6px;
            }
            p {
                margin-top: 0;
                margin-bottom: 16px;
                color: #9ca3af;
            }
            #controls {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }
            #dropzone {
                border: 2px dashed #4b5563;
                border-radius: 12px;
                width: 320px;
                height: 220px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: background 0.2s, border-color 0.2s;
                text-align: center;
            }
            #dropzone.dragover {
                background: #1f2937;
                border-color: #10b981;
            }
            #preview {
                margin-top: 20px;
                max-width: 200px;
                border-radius: 8px;
                border: 1px solid #374151;
            }
            #result {
                margin-top: 20px;
                font-size: 1.0rem;
                max-width: 600px;
                text-align: center;
                white-space: pre-wrap;
                word-break: break-word;
            }
            #jsonResult {
                margin-top: 10px;
                max-width: 600px;
                background: #020617;
                border-radius: 8px;
                padding: 10px 12px;
                border: 1px solid #374151;
                text-align: left;
                font-family: "Fira Code", "Consolas", monospace;
                font-size: 0.85rem;
                white-space: pre-wrap;
                word-break: break-word;
            }
            #loader {
                margin-top: 15px;
                display: none;
            }
            button {
                padding: 8px 14px;
                border-radius: 8px;
                border: none;
                background: #10b981;
                color: #111827;
                font-weight: 600;
                cursor: pointer;
            }
            button.secondary {
                background: #ef4444;
                color: #f9fafb;
            }
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            #top-msg {
                font-size: 0.9rem;
                color: #9ca3af;
                margin-bottom: 18px;
            }
        </style>
    </head>
    <body>
        <h1>Federated Learning - Master UI</h1>
        <div id="top-msg">Start or Stop the training and perform inference with an image.</div>

        <div id="controls">
            <button id="btnStart">Start Federated Loop</button>
            <button id="btnStop" class="secondary">Stop Training</button>
        </div>

        <h2>Inference</h2>
        <p>Drag an image here (e.g., MNIST-like digit) to perform inference on the master.</p>

        <div id="dropzone">
            <span>Drag an image here<br/>or click to select</span>
            <input id="fileInput" type="file" accept="image/*" style="display:none" />
        </div>

        <img id="preview" src="" alt="" style="display:none;" />
        <div id="loader">Operation running...</div>

        <div id="result"></div>
        <pre id="jsonResult"></pre>

        <script>
            console.log("UI script loaded");

            const dropzone = document.getElementById('dropzone');
            const fileInput = document.getElementById('fileInput');
            const preview = document.getElementById('preview');
            const resultDiv = document.getElementById('result');
            const loader = document.getElementById('loader');
            const jsonResult = document.getElementById('jsonResult');

            const btnStart = document.getElementById('btnStart');
            const btnStop = document.getElementById('btnStop');

            function resetUI() {
                resultDiv.textContent = "";
                jsonResult.textContent = "";
                loader.style.display = "none";
            }

            // =======================
            //  CHIAMATE AI BOTTONI
            // =======================
            btnStart.addEventListener('click', () => {
                resetUI();
                loader.style.display = "block";
                resultDiv.textContent = "Starting federated_loop...";

                fetch("/iotronic/boards/FL_master/federated_loop")
                    .then(res => res.json())
                    .then(data => {
                        loader.style.display = "none";
                        resultDiv.textContent = "Response federated_loop:";
                        jsonResult.textContent = JSON.stringify(data, null, 2);
                    })
                    .catch(err => {
                        loader.style.display = "none";
                        resultDiv.textContent = "Error in federated_loop: " + err;
                    });
            });

            btnStop.addEventListener('click', () => {
                resetUI();
                loader.style.display = "block";
                resultDiv.textContent = "Stopping training...";

                fetch("/iotronic/boards/FL_master/stop_training")
                    .then(res => res.json())
                    .then(data => {
                        loader.style.display = "none";
                        resultDiv.textContent = "Response stop_training:";
                        jsonResult.textContent = JSON.stringify(data, null, 2);
                    })
                    .catch(err => {
                        loader.style.display = "none";
                        resultDiv.textContent = "Error in stop_training: " + err;
                    });
            });

            // =======================
            //   IMAGE HANDLING
            // =======================
            function handleFiles(files) {
                console.log("handleFiles called", files);
                if (!files || files.length === 0) return;
                const file = files[0];
                resetUI();

                // Preview locale
                const reader = new FileReader();
                reader.onload = (e) => {
                    console.log("FileReader onload");
                    preview.src = e.target.result;
                    preview.style.display = "block";
                };
                reader.readAsDataURL(file);

                // Invia al backend per inferenza
                const formData = new FormData();
                formData.append("file", file);

                loader.style.display = "block";
                resultDiv.textContent = "";

                fetch("/iotronic/boards/FL_master/perform_inference", {
                    method: "POST",
                    body: formData
                })
                .then(res => res.json())
                .then(data => {
                    loader.style.display = "none";
                    console.log("Inference response", data);

                    // data è del tipo:
                    // {
                    //   board: "FL_master",
                    //   data: {
                    //     predicted_index: 9,
                    //     probabilities: [...]
                    //   },
                    //   _links: {...}
                    // }

                    const inner = data.data || {};
                    const pred = inner.predicted_index;
                    const probs = inner.probabilities || [];

                    resultDiv.textContent = "Prediction: " + pred;

                    // Mostra solo la parte rilevante nel riquadro JSON
                    jsonResult.textContent = JSON.stringify(
                        {
                            predicted_index: pred,
                            probabilities: probs
                        },
                        null,
                        2
                    );
                })
                .catch(err => {
                    loader.style.display = "none";
                    console.error("Network error", err);
                    resultDiv.textContent = "Network error " + err;
                });
            }

            dropzone.addEventListener('click', () => {
                console.log("Dropzone click");
                fileInput.click();
            });

            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            });

            dropzone.addEventListener('dragleave', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            });

            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                console.log("Drop event", files);
                handleFiles(files);
            });

            fileInput.addEventListener('change', (e) => {
                const files = e.target.files;
                console.log("File input change", files);
                handleFiles(files);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ===============================
#   ENDPOINT: UPLOAD + RPC
# ===============================

@app.post("/iotronic/boards/FL_master/perform_inference")
async def FL_master_perform_inference(file: UploadFile = File(...)):
    if not wamp_session:
        raise HTTPException(status_code=503, detail="WAMP non pronto")

    content = await file.read()
    image_b64 = base64.b64encode(content).decode("ascii")

    payload = {
        "image_base64": image_b64,
        "format": "png"
    }

    result = await wamp_session.call(
        f"iotronic.{master_hostname}.perform_inference",
        payload
    )

    return {
        "board": "FL_master",
        "data": result,
        "_links": {
            "self": {
                "href": f"/iotronic/boards/FL_master/perform_inference"
            }
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4053)
