from boto3.session import Session
from chalice import Chalice

from chalicelib import Handler, Sender, Storage

app = Chalice(app_name="ws_server")
app.websocket_api.session = Session()
app.experimental_feature_flags.update(["WEBSOCKETS"])

STORAGE = Storage.from_env()
SENDER = Sender(app, STORAGE)
HANDLER = Handler(STORAGE, SENDER)


@app.on_ws_connect()
def connect(event):
    STORAGE.create_connection(event.connection_id)


@app.on_ws_disconnect()
def disconnect(event):
    STORAGE.delete_connection(event.connection_id)


@app.on_ws_message()
def message(event):
    HANDLER.handle(event.connection_id, event.body)
