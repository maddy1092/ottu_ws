First implementation based on [AWS Websocket Tutorial - Chat Server Example](https://aws.github.io/chalice/tutorials/websockets#chat-server-example)

## Deployment

```shell
export AWS_DEFAULT_REGION=eu-west-1
export BUCKET=ottu_ws

# prod
chalice package --merge-template resources.json out
# dev
chalice package --merge-template resources.dev.json out

# prod
export STACK_NAME=OttuWsNotify
# dev 
export STACK_NAME=OttuWsNotify


aws cloudformation package  --template-file out/sam.json --s3-bucket $BUCKET --output-template-file out/template.yml

aws cloudformation deploy --template-file out/template.yml --stack-name $STACK_NAME --capabilities CAPABILITY_IAM
```

## UPDATE Lambda

```shell

export AWS_DEFAULT_REGION=eu-west-1
export BUCKET=ws_server

chalice package --merge-template resources.dev.json out

aws cloudformation package  --template-file out/sam.json --s3-bucket ottu-ws --output-template-file out/template.yml

aws cloudformation deploy --template-file out/template.yml --stack-name OttuWsNotify --capabilities CAPABILITY_IAM
```

### Deployment URL:

```shell
aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='WebsocketConnectEndpointURL'].OutputValue" --output text
```

## Backend Integrations

```python
import websocket
import json
ws_notify_url = ""
payload_dict = {
            "merchant_id": "merchant_id",
            "client": "backend",
            "project": "repo-name",
            "type": "report.Task",
            "ref": "12303",
            "status": "done",
            "message": "The report has been completed"
            }

payload = json.dumps(payload_dict)

ws = websocket.WebSocket()
ws.connect("ws_notify_url")

ws.send(payload)
ws.close()
```


## Message SDK Implementation

```javascript
const socket = new WebSocket('wss://10h4atbflh.execute-api.eu-west-1.amazonaws.com/dev/');

socket.addEventListener('message', function (event) {
    console.log('Message from server ', event.data);
    response = JSON.parse(event.data)

    if (response.type =='threeds_update') {
      //socket.send("Delete connection")
      socket.close();
      //do_something();
    }
});

socket.send('{"merchant_id": "merchant_id",
            "client": "backend",
            "project": "repo-name",
            "type": "report.Task",
            "ref": "12303",
            "status": "done",
            "message": "The report has been completed"}');


//On next iteration
socket.addEventListener('open', function (event) {
    socket.send('{"merchant_id": "merchant_id",
            "client": "backend",
            "project": "repo-name",
            "type": "report.Task",
            "ref": "12303",
            "status": "done",
            "message": "The report has been completed"}');
});
```

## For Backend Use

```shell

from boto3.session import Session
from chalice import Chalice
from chalicelib import Handler, Sender, Storage

app = Chalice(app_name="ws_server")
app.websocket_api.session = Session()
app.experimental_feature_flags.update(["WEBSOCKETS"])

STORAGE = Storage.from_env()
SENDER = Sender(app, STORAGE)
HANDLER = Handler(STORAGE, SENDER)

## To create a connection in DynamoDB
STORAGE.create_connection("3", '{"merchant_id": "merchant_id",
                          "client": "backend",
                          "project": "repo-name",
                          "type": "report.Task",
                          "ref": "12303",
                          "status": "done",
                          "message": "The report has been completed"}')

                          
## To delete a connection from DynamoDB
STORAGE.delete_connection('{"merchant_id": "merchant_id","ref":"12303"}')

##To pass a message
HANDLER.handle("1", '{"merchant_id": "merchant_id",
                "client": "backend",
                "project": "repo-name",
                "type": "report.Task",
                "ref": "12303",
                "status": "done",
                "message": "The report has been completed"}')
```

## For Frontend Use

# Websocket connect
wss://121212.execute-api.ap-south-1.amazonaws.com/dev/connect

# Websocket disconnect
wss://121212.execute-api.ap-south-1.amazonaws.com/dev/disconnect

# Websocket send message
wss://121212.execute-api.ap-south-1.amazonaws.com/dev/default

# Required Payload
```
{
    "merchant_id": "merchant_id",
    "client": "frontend" // or backend
    "project": "repo-name", //
    "type": "report.Task", // app_name.Model if db related, else a unique type, like report_task
    "ref": "12303", // pk if model, else a unique reference in the project by which the task can be identified
    "status": "done", // or failed
    "message": "The report has been completed", // or the error message if failed
}
```