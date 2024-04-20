import json
from unittest.mock import Mock

import pytest
from chalice import Chalice

from chalicelib import Handler, Sender, Storage

app = Chalice(app_name="ws_server")

STORAGE = Storage.from_env()
SENDER = Sender(app, STORAGE)
HANDLER = Handler(STORAGE, SENDER)

# static input data:
user_id = "72"
user_ids = ["72"]
connection_id = "1092"
ts = "1092387456"
merchant_id = "staging.ottu.dev"
type = "frontend"
backend_data = {
    "id": {
        "merchant_id": "staging4.ottu.dev",
        "client": "core_backend",
        "type": "backend",
    },
    "target": {"plugin": "report", "model": "Report", "ref": "18"},
    "audience": {"data": "__all__", "message": ["72"]},
    "content": {
        "alert": "success",
        "message": "Payment request report generation has finished.",
        "data": {
            "id": 18,
            "status": "FINISHED",
            "type": "Payment request",
            "file": "https://staging4.ottu.dev/media/exported_report_18.csv",
            "size": 25562,
            "file_format": "csv",
            "records_amount": 29,
            "period": "05 Jul, 2022, 08:27 AM - 02 Sep, 2022, 07:35 AM",
            "created_at": "11 Oct, 2022, 03:24 PM",
            "exported_at": "11 Oct, 2022, 03:24 PM",
            "username": "superadmin",
        },
        "action": "redirect",
    },
    "timestamp": "2022-10-11 15:25:39:003823",
}
item = {
    "PK": connection_id,
    "merchant_id": merchant_id,
    "user_id": user_id,  # user_id will be stored if true else null string
    "ExpirationTime": ts,
}

# static output data
existing_user = [{"cid": "1092", "user_id": "72"}]
non_existing_user = []


class TestMainHandler:
    # store frontend reference in db
    # Here we are storing the object in dynamoDB using
    # connection_id as a primary key.

    def test_set_user_by_connection_id(self):
        STORAGE._table = Mock()
        STORAGE._table.put_item = Mock()
        STORAGE._table.put_item.return_value = []
        result = STORAGE.set_user_by_connection_id(
            connection_id, merchant_id, user_id, ts
        )
        STORAGE._table.put_item.assert_called_once_with(Item=item)
        assert result == "1092"

    # fetch user stored in DB by connection_id
    # Here we are fetching the user_id that is
    # already stored in dynamoDB using
    # connection_id as a primary key.

    def test_get_existing_connection_ids_by_reference(self):
        STORAGE._table = Mock()
        STORAGE._table.scan = Mock()
        STORAGE._table.scan.return_value = {
            "Items": [
                {"PK": "1092", "merchant_id": "staging_ottu_dev", "user_id": "72"}
            ],
            "start_key": None,
        }

        result = STORAGE.get_connection_ids_by_reference(merchant_id, user_ids)
        assert result == existing_user

    # fetch user not stored in DB by connection_id
    # Here we are fetching the user_id that does
    # not exists in dynamoDB using
    # connection_id as a primary key. Output would be []

    def test_get_non_existing_connection_ids_by_reference(self):
        STORAGE._table = Mock()
        STORAGE._table.scan = Mock()
        STORAGE._table.scan.return_value = {"Items": [], "start_key": None}

        result = STORAGE.get_connection_ids_by_reference(merchant_id, user_ids)
        assert result == non_existing_user

    def test_delete_connection(self):
        STORAGE._table = Mock()
        STORAGE._table.delete_item = Mock()
        STORAGE._table.delete_item.return_value = []
        result = STORAGE.delete_connection(connection_id)
        STORAGE._table.delete_item.assert_called_once_with(Key={"PK": connection_id})
        assert result == connection_id

    def test_handle_frontend(self):
        STORAGE.set_user_by_connection_id = Mock()
        STORAGE.set_user_by_connection_id.return_value = "1092"
        result = HANDLER.handle_frontend(connection_id, merchant_id, user_id)
        assert connection_id == result

    def test_handle_frontend_with_invalid_params(self):
        STORAGE.set_user_by_connection_id = Mock()
        STORAGE.set_user_by_connection_id.return_value = "1092"
        with pytest.raises(TypeError):
            HANDLER.handle_frontend(connection_id, "", "")

    def test_handle_backend(self):
        STORAGE.get_connection_ids_by_reference = Mock()
        STORAGE.get_connection_ids_by_reference.return_value = existing_user
        result = HANDLER.handle_backend(merchant_id, user_id)
        assert existing_user == result

    def test_handle_backend_with_invalid_params(self):
        STORAGE.get_connection_ids_by_reference = Mock()
        STORAGE.get_connection_ids_by_reference.return_value = existing_user
        with pytest.raises(TypeError):
            HANDLER.handle_frontend(connection_id, "", "")

    def test_broadcast(self):
        SENDER.send = Mock()
        SENDER.send.return_value = []
        SENDER.broadcast(existing_user, backend_data)
        # self.assertEqual(existing_user, result)
        SENDER.send.assert_called_once_with(connection_id, json.dumps(backend_data))
