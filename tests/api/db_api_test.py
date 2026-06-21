import unittest
from uuid import uuid4
from unittest.mock import patch

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept import BlobObject, Flowcept, WorkflowObject, AgentObject
from flowcept.configs import MONGO_ENABLED, LMDB_ENABLED
from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class OurObject:
    def __init__(self):
        self.a = 1
        self.b = 2

    def __str__(self):
        return f"It worked! {self.a} {self.b}"


class DBAPITest(unittest.TestCase):
    def tearDown(self):
        """Close shared DAO singleton to avoid leaked DB clients between tests."""
        instance = DocumentDBDAO._instance
        if instance is not None:
            instance.close()

    def test_wf_dao(self):
        workflow1_id = str(uuid4())
        wf1 = WorkflowObject()
        wf1.workflow_id = workflow1_id

        assert Flowcept.db.insert_or_update_workflow(wf1)

        wf1.custom_metadata = {"test": "abc"}
        assert Flowcept.db.insert_or_update_workflow(wf1)

        wf_obj = Flowcept.db.get_workflow_object(workflow_id=workflow1_id)
        assert wf_obj is not None
        print(wf_obj)

    def test_agent_dao(self):
        agent_id = str(uuid4())
        agent = AgentObject(agent_id=agent_id, name="TestAgent")
        agent.enrich()

        # Check registered_at is populated and is a float
        assert agent.registered_at is not None
        assert isinstance(agent.registered_at, float)

        assert Flowcept.db.insert_or_update_agent(agent)

        agent_obj = Flowcept.db.get_agent_object(agent_id=agent_id)
        assert agent_obj is not None
        assert agent_obj.name == "TestAgent"
        assert agent_obj.agent_id == agent_id
        assert agent_obj.registered_at == agent.registered_at

    def test_agent_dao_both_db_paths(self):
        from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
        from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO
        from flowcept.configs import MONGO_ENABLED, LMDB_ENABLED

        agent_id = str(uuid4())
        agent = AgentObject(agent_id=agent_id, name="DBTestAgent")
        agent.enrich()

        if MONGO_ENABLED:
            mongo_dao = MongoDBDAO()
            assert mongo_dao.insert_or_update_agent(agent)
            res = mongo_dao.agent_query(filter={"agent_id": agent_id})
            assert len(res) == 1
            assert res[0]["name"] == "DBTestAgent"
            assert res[0]["registered_at"] == agent.registered_at

        if LMDB_ENABLED:
            lmdb_dao = LMDBDAO()
            assert lmdb_dao.insert_or_update_agent(agent)
            res = lmdb_dao.agent_query(filter={"agent_id": agent_id})
            assert len(res) == 1
            assert res[0]["name"] == "DBTestAgent"
            assert res[0]["registered_at"] == agent.registered_at

    def test_flowcept_agent_instantiation(self):
        agent_id = str(uuid4())
        agent_name = "InstantiatedAgent"

        with Flowcept(agent_id=agent_id, agent_name=agent_name, save_workflow=False, start_persistence=False):
            agent_msgs = [msg for msg in Flowcept.buffer if msg.get("type") == "agent"]

        assert len(agent_msgs) == 1
        assert agent_msgs[0]["agent_id"] == agent_id
        assert agent_msgs[0]["name"] == agent_name
        assert agent_msgs[0]["registered_at"] is not None

    def test_flowcept_agent_name_generates_agent_id(self):
        agent_name = "GeneratedIdAgent"

        with Flowcept(agent_name=agent_name, save_workflow=False, start_persistence=False) as fc:
            agent_id = fc.agent_id
            agent_msgs = [msg for msg in Flowcept.buffer if msg.get("type") == "agent"]

        assert agent_id is not None
        assert len(agent_msgs) == 1
        assert agent_msgs[0]["agent_id"] == agent_id
        assert agent_msgs[0]["name"] == agent_name

    def test_workflow_dao_update_fields(self):
        wf2_id = str(uuid4())
        print(wf2_id)

        wf2 = WorkflowObject()
        wf2.workflow_id = wf2_id

        tel = TelemetryCapture()
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["123"]
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["1234"]
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        if MONGO_ENABLED:
            # TODO: note that some of these tests currently only work on MongoDB because
            #  updating is not yet implemented in LMDB
            assert len(wf_obj.interceptor_ids) == 2
        wf2.machine_info = {"123": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        assert wf_obj
        wf2.machine_info = {"1234": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        if MONGO_ENABLED:
            assert len(wf_obj.machine_info) == 2

    def test_workflow_enrich_redacts_sensitive_settings(self):
        wf = WorkflowObject()
        test_settings = {
            "mq": {"password": "redis-pass", "host": "localhost"},
            "kv_db": {"passwd": "kv-pass"},
            "agent": {"api_key": "agent-key"},
        }

        with patch("flowcept.commons.flowcept_dataclasses.workflow_object.settings", test_settings):
            wf.enrich()

        assert wf.flowcept_settings["mq"].get("password") == "REDACTED"
        assert wf.flowcept_settings["mq"].get("host") == "localhost"
        assert wf.flowcept_settings["kv_db"].get("passwd") == "REDACTED"
        assert wf.flowcept_settings["agent"].get("api_key") == "REDACTED"

    def test_workflow_to_dict_redacts_sensitive_settings(self):
        wf = WorkflowObject()
        wf.flowcept_settings = {"mq": {"password": "redis-pass"}, "agent": {"api_key": "agent-key"}}

        wf_dict = wf.to_dict()

        assert wf_dict["flowcept_settings"]["mq"]["password"] == "REDACTED"
        assert wf_dict["flowcept_settings"]["agent"]["api_key"] == "REDACTED"
        assert "redis-pass" not in str(wf_dict)
        assert "agent-key" not in str(wf_dict)

    def test_workflow_dynamic_schema_snapshot_roundtrip(self):
        workflow_id = str(uuid4())
        wf = WorkflowObject()
        wf.workflow_id = workflow_id
        wf.name = "schema snapshot workflow"
        wf.custom_metadata = {"owner": "existing"}
        assert Flowcept.db.insert_or_update_workflow(wf)

        snapshot = {
            "dynamic_schema": {"step_a": {"i": ["used.input_value"], "o": ["generated.output_value"]}},
            "value_examples": {"input_value": {"t": "int", "v": [1]}},
            "current_fields": ["workflow_id", "activity_id", "used.input_value", "generated.output_value"],
        }

        assert Flowcept.db.save_workflow_domain_data_schema(workflow_id, snapshot)

        loaded = Flowcept.db.get_workflow_domain_data_schema(workflow_id)
        wf_obj = Flowcept.db.get_workflow_object(workflow_id)

        assert loaded == snapshot
        assert wf_obj.workflow_domain_data_schema == snapshot
        assert wf_obj.name == "schema snapshot workflow"
        assert wf_obj.custom_metadata["owner"] == "existing"
        assert "dynamic_schema_snapshot" not in wf_obj.custom_metadata

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_save_blob(self):
        import pickle

        obj = pickle.dumps(OurObject())

        obj_id = Flowcept.db.save_or_update_object(object=obj, save_data_in_collection=True)
        print(obj_id)

        obj_docs = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")
        loaded_obj = pickle.loads(obj_docs[0]["data"])
        assert type(loaded_obj) == OurObject

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_object_query_and_get(self):
        payload = b"blob-content"
        with Flowcept(workflow_name="blob_demo"):
            obj_id = Flowcept.db.save_or_update_object(
                object=payload,
                task_id="task_blob_1",
                object_type="artifact",
                custom_metadata={"owner": "tests"},
                save_data_in_collection=True,
            )
            expected_wf_id = Flowcept.current_workflow_id

            docs = Flowcept.db.blob_object_query(filter={"object_id": obj_id})
            assert docs is not None
            assert len(docs) == 1
            assert docs[0]["object_id"] == obj_id
            assert docs[0]["data"] == payload

            blob = Flowcept.db.get_blob_object(obj_id)
            assert isinstance(blob, BlobObject)
            assert blob.object_id == obj_id
            assert blob.task_id == "task_blob_1"
            assert blob.workflow_id == expected_wf_id
            assert blob.object_type == "artifact"
            assert blob.custom_metadata["owner"] == "tests"
            assert blob.version == 0

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_save_blob_emits_object_metadata_message(self):
        object_messages = []
        with Flowcept(workflow_name="blob_message_demo", start_persistence=False):
            with patch.object(Flowcept, "emit_message", side_effect=object_messages.append):
                obj_id = Flowcept.db.save_or_update_object(
                    object=b"blob-message-content",
                    task_id="task_blob_message",
                    object_type="artifact",
                    custom_metadata={"owner": "tests"},
                    save_data_in_collection=True,
                )

        assert len(object_messages) == 1
        object_msg = object_messages[0]
        assert object_msg["object_id"] == obj_id
        assert object_msg["object_type"] == "artifact"
        assert object_msg["task_id"] == "task_blob_message"
        assert object_msg["workflow_id"] is not None
        assert object_msg["custom_metadata"]["owner"] == "tests"
        assert "data" not in object_msg

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_object_version_control(self):
        obj_id = str(uuid4())
        payload_v0 = b"v0"
        Flowcept.db.save_or_update_object(
            object=payload_v0,
            object_id=obj_id,
            object_type="artifact",
            save_data_in_collection=True,
        )
        blob_v0 = Flowcept.db.get_blob_object(obj_id)
        assert blob_v0.version == 0
        doc_v0 = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
        assert doc_v0["data"] == payload_v0

        payload_v1 = b"v1"
        Flowcept.db.save_or_update_object(
            object=payload_v1,
            object_id=obj_id,
            object_type="artifact",
            save_data_in_collection=True,
        )
        blob_v1 = Flowcept.db.get_blob_object(obj_id)
        assert blob_v1.version == 1
        doc_v1 = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
        assert doc_v1["data"] == payload_v1

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_object_store_in_gridfs(self):
        with Flowcept(workflow_name="blob_gridfs_test"):
            expected_wf_id = Flowcept.current_workflow_id
            payload = b"gridfs-content-v0"
            obj_id = Flowcept.db.save_or_update_object(
                object=payload,
                task_id="task_gridfs_1",
                object_type="artifact",
                save_data_in_collection=False,
            )

            blob = Flowcept.db.get_blob_object(obj_id)
            assert blob.workflow_id == expected_wf_id
            assert blob.version == 0

            doc = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
            assert "data" not in doc
            assert "grid_fs_file_id" in doc
            retrieved = Flowcept.db._dao().get_file_data(doc["grid_fs_file_id"])
            assert retrieved == payload

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_object_store_in_gridfs_update(self):
        with Flowcept(workflow_name="blob_gridfs_update_test"):
            expected_wf_id = Flowcept.current_workflow_id
            obj_id = str(uuid4())
            payload_v0 = b"gridfs-content-v0"
            Flowcept.db.save_or_update_object(
                object=payload_v0,
                object_id=obj_id,
                object_type="artifact",
                save_data_in_collection=False,
            )

            doc_v0 = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
            retrieved_v0 = Flowcept.db._dao().get_file_data(doc_v0["grid_fs_file_id"])
            assert retrieved_v0 == payload_v0

            payload_v1 = b"gridfs-content-v1"
            Flowcept.db.save_or_update_object(
                object=payload_v1,
                object_id=obj_id,
                object_type="artifact",
                save_data_in_collection=False,
            )

            blob_v1 = Flowcept.db.get_blob_object(obj_id)
            assert blob_v1.workflow_id == expected_wf_id
            assert blob_v1.version == 1

            doc_v1 = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
            assert "data" not in doc_v1
            assert "grid_fs_file_id" in doc_v1
            retrieved_v1 = Flowcept.db._dao().get_file_data(doc_v1["grid_fs_file_id"])
            assert retrieved_v1 == payload_v1

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_fingerprint_and_equality_in_object(self):
        with Flowcept(workflow_name="blob_fingerprint_test"):
            payload = b"equal-payload"
            obj_id_a = Flowcept.db.save_or_update_object(
                object=payload,
                object_type="artifact",
                save_data_in_collection=True,
            )
            obj_id_b = Flowcept.db.save_or_update_object(
                object=payload,
                object_type="artifact",
                save_data_in_collection=True,
            )
            obj_id_c = Flowcept.db.save_or_update_object(
                object=b"different-payload",
                object_type="artifact",
                save_data_in_collection=True,
            )

            fp_a = Flowcept.db.get_blob_fingerprint(obj_id_a)
            assert fp_a["data_hash_algo"] == "sha256"
            assert fp_a["data_sha256"] is not None
            assert fp_a["object_size_bytes"] == len(payload)

            assert Flowcept.db.blob_objects_equal(obj_id_a, obj_id_b)
            assert not Flowcept.db.blob_objects_equal(obj_id_a, obj_id_c)

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_blob_fingerprint_and_equality_gridfs(self):
        with Flowcept(workflow_name="blob_fingerprint_gridfs_test"):
            payload = b"gridfs-equal-payload"
            obj_id_a = Flowcept.db.save_or_update_object(
                object=payload,
                object_type="artifact",
                save_data_in_collection=False,
            )
            obj_id_b = Flowcept.db.save_or_update_object(
                object=payload,
                object_type="artifact",
                save_data_in_collection=False,
            )
            obj_id_c = Flowcept.db.save_or_update_object(
                object=b"gridfs-different-payload",
                object_type="artifact",
                save_data_in_collection=False,
            )

            fp_a = Flowcept.db.get_blob_fingerprint(obj_id_a)
            assert fp_a["storage_type"] == "gridfs"
            assert fp_a["data_hash_algo"] == "sha256"
            assert fp_a["data_sha256"] is not None

            assert Flowcept.db.blob_objects_equal(obj_id_a, obj_id_b)
            assert not Flowcept.db.blob_objects_equal(obj_id_a, obj_id_c)

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_ml_model_aliases(self):
        payload = b"model-bytes"
        with Flowcept(workflow_name="ml_model_alias_test"):
            obj_id = Flowcept.db.save_or_update_ml_model(
                object=payload,
                task_id="task_model_1",
                save_data_in_collection=True,
            )
            expected_wf_id = Flowcept.current_workflow_id

            blob = Flowcept.db.get_ml_model(obj_id)
            assert isinstance(blob, BlobObject)
            assert blob.object_id == obj_id
            assert blob.object_type == "ml_model"
            assert blob.task_id == "task_model_1"
            assert blob.workflow_id == expected_wf_id

            docs = Flowcept.db.ml_model_query(filter={"object_id": obj_id, "object_type": "ml_model"})
            assert docs is not None
            assert len(docs) == 1
            assert docs[0]["data"] == payload

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_dataset_aliases(self):
        payload = b"dataset-bytes"
        with Flowcept(workflow_name="dataset_alias_test"):
            obj_id = Flowcept.db.save_or_update_dataset(
                object=payload,
                task_id="task_dataset_1",
                save_data_in_collection=True,
            )
            expected_wf_id = Flowcept.current_workflow_id

            blob = Flowcept.db.get_dataset(obj_id)
            assert isinstance(blob, BlobObject)
            assert blob.object_id == obj_id
            assert blob.object_type == "dataset"
            assert blob.task_id == "task_dataset_1"
            assert blob.workflow_id == expected_wf_id

            docs = Flowcept.db.dataset_query(filter={"object_id": obj_id, "object_type": "dataset"})
            assert docs is not None
            assert len(docs) == 1
            assert docs[0]["data"] == payload

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_save_object_defaults_workflow_id_from_current_workflow(self):
        with Flowcept(workflow_name="blob_default_wf_test"):
            current_wf_id = Flowcept.current_workflow_id
            obj_id = Flowcept.db.save_or_update_object(
                object=b"default-wf-content",
                task_id="task_default_wf",
                object_type="artifact",
                save_data_in_collection=True,
            )

        blob = Flowcept.db.get_blob_object(obj_id)
        assert blob.workflow_id == current_wf_id

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_control_version_first_insert(self):
        with Flowcept(workflow_name="blob_control_first_insert"):
            payload = b"cv-v1"
            obj_id = Flowcept.db.save_or_update_object(
                object=payload,
                task_id="task_cv_1",
                object_type="artifact",
                save_data_in_collection=True,
                control_version=True,
            )
            latest = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")[0]
            assert latest["version"] == 0
            assert latest["prev_version"] is None
            assert "created_at" in latest
            assert "updated_at" in latest
            history_docs = Flowcept.db.query(filter={"object_id": obj_id}, collection="object_history")
            assert len(history_docs) == 0
            blob_latest = Flowcept.db.get_blob_object(obj_id)
            assert blob_latest.version == 0
            assert getattr(blob_latest, "data") == payload

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_control_version_update_and_history_in_object(self):
        with Flowcept(workflow_name="blob_control_update_in_object"):
            payload_v1 = b"cv-in-object-v1"
            payload_v2 = b"cv-in-object-v2"
            obj_id = Flowcept.db.save_or_update_object(
                object=payload_v1,
                object_type="artifact",
                save_data_in_collection=True,
                control_version=True,
            )
            Flowcept.db.save_or_update_object(
                object=payload_v2,
                object_id=obj_id,
                object_type="artifact",
                save_data_in_collection=True,
                control_version=True,
            )

            latest = Flowcept.db.get_blob_object(obj_id)
            hist = Flowcept.db.get_blob_object(obj_id, version=0)
            assert latest.version == 1
            assert getattr(latest, "data") == payload_v2
            assert hist.version == 0
            assert getattr(hist, "data") == payload_v1

            history_docs = Flowcept.db.query(filter={"object_id": obj_id}, collection="object_history")
            assert len(history_docs) == 1
            assert history_docs[0]["version"] == 0

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_control_version_update_and_history_gridfs(self):
        with Flowcept(workflow_name="blob_control_update_gridfs"):
            payload_v1 = b"cv-gridfs-v1"
            payload_v2 = b"cv-gridfs-v2"
            obj_id = Flowcept.db.save_or_update_object(
                object=payload_v1,
                object_type="artifact",
                save_data_in_collection=False,
                control_version=True,
            )
            Flowcept.db.save_or_update_object(
                object=payload_v2,
                object_id=obj_id,
                object_type="artifact",
                save_data_in_collection=False,
                control_version=True,
            )
            latest = Flowcept.db.get_blob_object(obj_id)
            hist = Flowcept.db.get_blob_object(obj_id, version=0)
            assert latest.version == 1
            assert getattr(latest, "data") == payload_v2
            assert hist.version == 0
            assert getattr(hist, "data") == payload_v1

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_get_object_history(self):
        with Flowcept(workflow_name="blob_list_versions"):
            obj_id = Flowcept.db.save_or_update_object(
                object=b"lv-v1",
                save_data_in_collection=True,
                control_version=True,
            )
            Flowcept.db.save_or_update_object(
                object=b"lv-v2",
                object_id=obj_id,
                save_data_in_collection=True,
                control_version=True,
            )
            versions = Flowcept.db.get_object_history(obj_id)
            assert [v["version"] for v in versions] == [1, 0]
            assert versions[0]["storage_type"] == "in_object"
            assert "data" not in versions[0]
            assert "grid_fs_file_id" not in versions[0]

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_control_version_retry_on_cas_mismatch(self):
        with Flowcept(workflow_name="blob_cas_retry"):
            obj_id = Flowcept.db.save_or_update_object(
                object=b"cas-v1",
                save_data_in_collection=True,
                control_version=True,
            )
            dao = Flowcept.db._dao()
            original = dao._update_with_optional_transaction
            calls = {"n": 0}

            def flaky_update(*args, **kwargs):
                if calls["n"] == 0:
                    calls["n"] += 1
                    return 0
                return original(*args, **kwargs)

            with patch.object(dao, "_update_with_optional_transaction", side_effect=flaky_update):
                Flowcept.db.save_or_update_object(
                    object=b"cas-v2",
                    object_id=obj_id,
                    save_data_in_collection=True,
                    control_version=True,
                )

            latest = Flowcept.db.get_blob_object(obj_id)
            assert latest.version == 1

    @unittest.skip("Test only for dev.")
    def test_tasks_recursive(self):
        mapping = {
            "activity_id": {
                "epochs_loop_iteration": [
                    "{'epoch': task['used']['epoch']}",
                    "{'model_train': ancestors[task['task_id']][-1]['task_id']}",
                ],
                "train_batch_iteration": [
                    "{'train_batch': task['used']['i'], 'train_data_path': ancestors[task['task_id']][0]['used']['train_data_path'], 'train_batch_size': ancestors[task['task_id']][0]['used']['batch_size'] }",
                    "{'epoch': ancestors[task['task_id']][-1]['used']['epoch']}",
                ],
                "eval_batch_iteration": [
                    "{'eval_batch': task['used']['i'], 'eval_data_path': ancestors[task['task_id']][0]['used']['val_data_path'], 'train_batch_size': ancestors[task['task_id']][0]['used']['eval_batch_size'] }",
                    "{'epoch': ancestors[task['task_id']][-1]['used']['epoch']}",
                ],
            },
            "subtype": {
                "parent_forward": [
                    "{'model': task['activity_id']}",
                    "ancestors[task['task_id']][-1]['custom_provenance_id']",
                ],
                "child_forward": [
                    "{'module': task['activity_id']}",
                    "ancestors[task['task_id']][-1]['custom_provenance_id']",
                ],
            },
        }
        Flowcept.db._dao().get_tasks_recursive("e9a3b567-cb56-4884-ba14-f137c0260191", mapping=mapping)

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_dump(self):
        wf_id = str(uuid4())

        c0 = Flowcept.db._dao().count_tasks()

        for i in range(10):
            t = TaskObject()
            t.workflow_id = wf_id
            t.task_id = str(uuid4())
            Flowcept.db.insert_or_update_task(t)

        _filter = {"workflow_id": wf_id}
        assert Flowcept.db.dump_to_file(
            filter=_filter,
        )
        assert Flowcept.db.dump_to_file(filter=_filter, should_zip=True)
        assert Flowcept.db.dump_to_file(filter=_filter, output_file="dump_test.json")

        Flowcept.db._dao().delete_tasks_with_filter(_filter)
        c1 = Flowcept.db._dao().count_tasks()
        assert c0 == c1

    def test_dashboard_crud_both_db_paths(self):
        """Dashboard CRUD works on both MongoDBDAO and LMDBDAO."""
        from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
        from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO

        dashboard_id = str(uuid4())
        doc = {
            "dashboard_id": dashboard_id,
            "dashboard_type": "common_workflow",
            "name": "test-dash",
            "charts": [],
            "layout": [],
        }

        if MONGO_ENABLED:
            dao = MongoDBDAO()
            assert dao.save_dashboard(doc)
            result = dao.get_dashboard(dashboard_id)
            assert result is not None
            assert result["name"] == "test-dash"
            all_docs = dao.list_dashboards()
            assert any(d["dashboard_id"] == dashboard_id for d in all_docs)
            filtered = dao.list_dashboards(filter={"dashboard_type": "common_workflow"})
            assert any(d["dashboard_id"] == dashboard_id for d in filtered)
            assert dao.delete_dashboard(dashboard_id)
            assert dao.get_dashboard(dashboard_id) is None
            dao.close()

        if LMDB_ENABLED:
            dao = LMDBDAO()
            assert dao.save_dashboard(doc)
            result = dao.get_dashboard(dashboard_id)
            assert result is not None
            assert result["name"] == "test-dash"
            all_docs = dao.list_dashboards()
            assert any(d["dashboard_id"] == dashboard_id for d in all_docs)
            filtered = dao.list_dashboards(filter={"dashboard_type": "common_workflow"})
            assert any(d["dashboard_id"] == dashboard_id for d in filtered)
            assert dao.delete_dashboard(dashboard_id)
            assert dao.get_dashboard(dashboard_id) is None
            dao.close()

    def test_dbapi_analytics_methods(self):
        """DBAPI exposes task_summary, derive_campaigns, derive_agents, telemetry_timeseries."""
        if not Flowcept.services_alive():
            import pytest
            pytest.skip("No live services.")
        db = Flowcept.db
        summary = db.task_summary({})
        assert isinstance(summary, dict)
        assert "count" in summary
        assert "status_counts" in summary
        assert "activity_stats" in summary
        assert "time_range" in summary

        campaigns = db.derive_campaigns()
        assert isinstance(campaigns, list)

        agents = db.derive_agents()
        assert isinstance(agents, list)

        rows = db.telemetry_timeseries({}, fields=["started_at"], x_field="started_at", limit=10)
        assert isinstance(rows, list)

    def test_dbapi_get_dao_instance(self):
        """DBAPI.get_dao_instance() returns the DocumentDBDAO singleton."""
        if not Flowcept.services_alive():
            import pytest
            pytest.skip("No live services.")
        from flowcept.flowcept_api.db_api import DBAPI
        dao = DBAPI.get_dao_instance()
        assert isinstance(dao, DocumentDBDAO)
        dashboard_id = str(uuid4())
        doc = {"dashboard_id": dashboard_id, "name": "test", "charts": []}
        assert dao.save_dashboard(doc) is True
        fetched = dao.get_dashboard(dashboard_id)
        assert fetched is not None
        assert fetched["dashboard_id"] == dashboard_id
        listed = dao.list_dashboards()
        assert any(d["dashboard_id"] == dashboard_id for d in listed)
        assert dao.delete_dashboard(dashboard_id) is True
        assert dao.get_dashboard(dashboard_id) is None

    def test_dbapi_resolve_chart_data(self):
        """DBAPI.resolve_chart_data returns rows and count for basic specs."""
        if not Flowcept.services_alive():
            import pytest
            pytest.skip("No live services.")
        from flowcept.flowcept_api.db_api import DBAPI
        db = DBAPI()
        result = db.resolve_chart_data({"source": "tasks", "filter": {}})
        assert isinstance(result, dict)
        assert "rows" in result and "count" in result
        assert isinstance(result["rows"], list)
        assert isinstance(result["count"], int)

        grouped = db.resolve_chart_data({
            "source": "tasks",
            "group_by": "status",
            "metrics": [{"field": "", "agg": "count"}],
        })
        assert isinstance(grouped, dict)
        assert "rows" in grouped and "count" in grouped

    def test_docdb_dao_utils(self):
        """Shared DAO helpers in docdb_dao_utils are importable and correct."""
        import pytest
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import (
            to_epoch,
            get_nested,
        )
        # epoch-ms → epoch-sec
        assert to_epoch(1_000_000_000_000) == pytest.approx(1_000_000_000.0)
        # already epoch-sec
        assert to_epoch(1_000_000_000.0) == pytest.approx(1_000_000_000.0)
        # ISO string (Unix 1000000000 = 2001-09-09T01:46:40Z)
        iso_result = to_epoch("2001-09-09T01:46:40+00:00")
        assert iso_result is not None
        assert abs(iso_result - 1_000_000_000.0) < 60  # within 1 minute of expected
        # None passthrough
        assert to_epoch(None) is None
        # dot-notated nested field
        assert get_nested({"a": {"b": 1}}, "a.b") == 1
        assert get_nested({"a": {"b": 1}}, "a.c") is None
        assert get_nested({"a": 1}, "a.b") is None
