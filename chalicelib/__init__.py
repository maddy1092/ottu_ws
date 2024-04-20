import copy
import json
import logging
import os
import time
import traceback

import boto3
import requests
from boto3.dynamodb.conditions import Key
from chalice import WebsocketDisconnectedError


class Storage:
    """An abstraction to interact with the DynamoDB Table."""

    def __init__(self, table):
        """Initialize Storage object

        :param table: A boto3 dynamodb Table resource object.
        """
        self._table = table

    @classmethod
    def from_env(cls):
        """Create table from the environment.

        The environment variable TABLE is present for a deployed application
        since it is set in all of the Lambda functions by a CloudFormation
        reference. We default to '', which will happen when we run
        ``chalice package`` since it loads the application, and no
        environment variable has been set. For local testing, a value should
        be manually set in the environment if '' will not suffice.
        """
        table_name = os.environ.get("TABLE", "OttuWsNotify")
        table = boto3.resource("dynamodb").Table(table_name)
        return cls(table)

    def create_connection(self, connection_id):
        """Create a new connection object in the database.

        When a new connection is created, we create a stub for
        it in the table. The stub uses a primary key of the
        connection_id and a sort key of reference_. This translates
        to a connection with an unset reference. The first message
        sent over the wire from the connection is to be used as the
        reference, and this entry will be re-written.

        :param connection_id: The connection id to write to
            the table.
        """

        logging.info(f"create_connection connection_id: {str(connection_id)}")

    def set_user_by_connection_id(self, connection_id, merchant_id, user_id, ts):
        """When we get payload from frontend, we extract
        merchant_id, user_id and type from the payload and store
        it in the table with connection_id as a primary key
        """

        try:
            # store data into db table received from message
            self._table.put_item(
                Item={
                    "PK": connection_id,
                    "merchant_id": merchant_id,
                    "user_id": user_id,  # user_id will be stored if true else null string
                    "ExpirationTime": ts,
                },
            )

        except Exception as e:
            logging.error(
                f"message_handle frontend ERROR: {(str(e), str(traceback.format_exc()))}"
            )
        return connection_id

    def get_connection_ids_by_reference(self, merchant_id, user_ids):
        """Find all connection ids that go to a room.

        This is needed whenever we broadcast to a room. We collect all
        their connection ids so we can send messages to them. We use a
        ReverseLookup table here which inverts the PK, merchant_id relationship
        creating a partition called room_{room}. Everything in that
        partition is a connection in the room.

        :param merchant_id: merchant id, ie: ksa.ottu.dev.
        :param ref: reference name to get all connection ids from.
        :param user_id: user id to send message to specific user
        """

        done = False
        data = []
        scan_kwargs = {}

        # scan_kwargs: A dict with field names and values for scan and items from table
        # by default two fields are medatory
        if user_ids == "__all__":
            scan_kwargs = {"FilterExpression": Key("merchant_id").eq(merchant_id)}
            while not done:
                response = self._table.scan(
                    **scan_kwargs
                )  # Scan table with provided field names and values
                data.extend(response.get("Items", []))
                start_key = response.get("LastEvaluatedKey", None)
                done = start_key is None

        else:
            for user_id in user_ids:
                scan_kwargs = {
                    "FilterExpression": Key("merchant_id").eq(merchant_id)
                    & Key("user_id").eq(f"{user_id}")
                }
                while not done:
                    response = self._table.scan(
                        **scan_kwargs
                    )  # Scan table with provided field names and values
                    data.extend(response.get("Items", []))
                    start_key = response.get("LastEvaluatedKey", None)
                    done = start_key is None

        return [{"cid": item["PK"], "user_id": item["user_id"]} for item in data]

    def delete_connection(self, connection_id):
        """Delete a connection.

        Called when a connection is disconnected and all its entries need
        to be deleted.

        """
        logging.info(f"delete_connection connection_id: {str(connection_id)}")

        if connection_id:
            try:
                self._table.delete_item(
                    Key={"PK": connection_id},
                )
            except Exception as e:
                logging.error(
                    f"delete_connection ERROR: {str(e)} - {str(traceback.format_exc())}"
                )
        return str(connection_id)


class Sender:
    """Class to send messages over websockets."""

    def __init__(self, app, storage):
        """Initialize a sender object.

        :param app: A Chalice application object.

        :param storage: A Storage object.
        """
        self._app = app
        self._storage = storage

    def send(self, connection_id, data):
        """Send a message over a websocket.

        :param connection_id: API Gateway Connection ID to send a
            message to.

        :param message: The message to send to the connection.
        """
        try:
            # Call the chalice websocket api send method
            self._app.websocket_api.send(connection_id, str(data))
        except WebsocketDisconnectedError as e:
            # If the websocket has been closed, we delete the connection
            # from our database.
            self._storage.delete_connection(connection_id)

    def broadcast(self, connection_ids, data):
        """ "Send a message to multiple connections.

        :param connection_ids: A list of API Gateway Connection IDs to
            send the message to.

        :param message: The message to send to the connections.
        """
        for cid in connection_ids:
            message_data = {}
            message_data = copy.deepcopy(data)

            if cid.get("user_id") in (data.get("audience").get("message")):
                self.send(cid.get("cid"), json.dumps(data))

            else:
                if message_data["content"]["message"]:
                    del message_data["content"]["message"]
                self.send(cid.get("cid"), json.dumps(message_data))
        return connection_ids


class Handler:
    """Handler object that handles messages received from a websocket.

    This class implements the bulk of our app behavior.
    """

    def __init__(self, storage, sender):
        """Initialize a Handler object.

        :param storage: Storage object to interact with database.

        :param sender: Sender object to send messages to websockets.
        """
        self._storage = storage
        self._sender = sender
        table_name = os.environ.get("TABLE", "OttuWsNotify")
        self._table = boto3.resource("dynamodb").Table(table_name)

    def handle(self, connection_id, message=None):
        """Entry point for our application.

        :param message: Message we got from the connection.
        """

        if message:
            data = json.loads(message)
            client = data.get("id").get("type")
            user_id = data.get("audience", {}).get("data", "")
            merchant_id = data.get("id", {}).get("merchant_id", "")

            # user_id : not required value
            # if not user_id leave it blank to maintain db table structure
            if client == "frontend":
                connection_id = self.handle_frontend(
                    connection_id, merchant_id, user_id
                )

            elif client == "backend":
                connection_ids = self.handle_backend(merchant_id, user_id)

                if connection_ids:
                    self._sender.broadcast(connection_ids, data)
            elif client == "ping":
                data = "pong"
                self._sender.send(connection_id, data)

            else:
                logging.error("message_handle client expecting frontend or backend")
        else:
            logging.error("message_handle message body not found")

    def handle_frontend(self, connection_id, merchant_id, user_id):
        ts = int(time.time())

        if merchant_id and user_id:
            self._storage.set_user_by_connection_id(
                connection_id, merchant_id, user_id, ts
            )
        else:
            raise TypeError("merchant_id and user_id is required")

        return connection_id

    def handle_backend(self, merchant_id, user_id):
        try:
            # below function will scan merchant_id and user_id
            # return list connection ids to broadcast
            # if not user_id then it will be null string
            if merchant_id and user_id:
                connection_ids = self._storage.get_connection_ids_by_reference(
                    merchant_id, user_id
                )
                logging.error(
                    f"connection ids : {connection_ids} | sessions : {requests.Session()}"
                )
            else:
                raise TypeError("merchant_id and user_id is required")

        except Exception as e:
            logging.error(
                f"message_handle backend ERROR: {str(e)} - {str(traceback.format_exc())}"
            )
            connection_ids = []

        return connection_ids
