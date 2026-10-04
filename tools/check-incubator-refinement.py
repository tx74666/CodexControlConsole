"""Disposable finite prompt-refinement outbox checks; never sends a chat."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_http import workflow_post
from workflow_service import WorkflowError, WorkflowService


def request(**fields):
    return {"requestId": str(uuid.uuid4()), **fields}


class RefinementChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="console-refinement-")
        self.data = Path(self.temp.name).resolve() / "private"
        self.service = WorkflowService(self.data)
        self.idea = self.service.incubator_create(request(title="想法", body="用户原稿", stage="thinking"))["idea"]
        self.thread = str(uuid.uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, **fields):
        return self.service.incubator_publish(request(id=self.idea["id"], expectedRevision=self.idea["revision"],
            targetKind="codex", targetMode="new", targetName="完善测试", purpose="refine", **fields))

    def claim(self):
        result = self.service.incubator_claim(request())
        self.assertTrue(result["shouldDispatch"])
        self.assertTrue(result["dispatch"]["userConfirmedAt"])
        return result["dispatch"]

    def finish(self, dispatch, text="<refined_prompt>完整新版正文</refined_prompt>", **fields):
        return self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            status="completed", targetThreadId=self.thread,
            result={"text": text, "turnId": "turn-" + dispatch["id"], "sourceMessageId": "source-" + dispatch["id"]}, **fields))

    def error(self, action, status=400):
        with self.assertRaises(WorkflowError) as caught:
            action()
        self.assertEqual(caught.exception.status, status)

    def test_three_finite_rounds_reuse_actual_target_and_reach_ready_without_execute(self):
        published = self.publish()
        session = published["refinement"]
        self.assertEqual(session["roundLimit"], 3)
        for number in range(1, 4):
            dispatch = self.claim()
            self.assertEqual(dispatch["purpose"], "refine")
            self.assertEqual(dispatch["round"], number)
            self.assertEqual(dispatch["refinementId"], session["id"])
            self.assertEqual(dispatch["userConfirmedAt"], session["userConfirmedAt"])
            self.assertIn("禁止执行任务", dispatch["prompt"])
            self.assertIn("<refined_prompt>", dispatch["prompt"])
            self.assertEqual(dispatch["targetMode"], "new" if number == 1 else "existing")
            if number > 1:
                self.assertEqual(dispatch["targetThreadId"], self.thread)
                self.assertIn("完整稿" + str(number - 1), dispatch["prompt"])
            result = self.finish(dispatch, "分析\n<refined_prompt>完整稿" + str(number) + "</refined_prompt>")
            self.assertEqual(result["dispatch"]["status"], "completed")
            self.assertEqual(result["idea"]["body"], "完整稿" + str(number))
        self.assertEqual(result["idea"]["stage"], "ready")
        self.assertEqual(result["refinement"]["state"], "completed")
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 3)
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])
        with self.service._db() as db:
            for table in ("records", "jobs", "messages"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)

    def test_round_limit_is_explicit_bounded_and_execute_behavior_unchanged(self):
        for value in (0, 11, True, "3", None):
            self.error(lambda value=value: self.publish(roundLimit=value))
        self.error(lambda: self.service.incubator_publish(request(id=self.idea["id"], expectedRevision=1,
            targetKind="codex", roundLimit=3)))
        published = self.publish(roundLimit=1)
        result = self.finish(self.claim())
        self.assertEqual(result["refinement"]["state"], "completed")
        self.assertEqual(result["idea"]["stage"], "ready")
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)
        separate = self.service.incubator_create(request(title="执行", body="执行授权稿"))["idea"]
        actual = self.service.incubator_publish(request(id=separate["id"], expectedRevision=1, targetKind="codex"))
        self.assertEqual(actual["dispatch"]["purpose"], "execute")
        executed = self.finish(self.claim(), "实际已有回答，不需要稿块")
        self.assertEqual(executed["idea"]["stage"], "published")

    def test_publication_and_completion_replays_do_not_create_extra_round(self):
        body = request(id=self.idea["id"], expectedRevision=1, targetKind="codex", purpose="refine")
        published = self.service.incubator_publish(body)
        self.assertTrue(self.service.incubator_publish(body)["duplicate"])
        dispatch = self.claim()
        result_body = request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="completed",
            targetThreadId=self.thread, result={"text": "<refined_prompt>新版</refined_prompt>", "turnId": "same-turn"})
        self.service.incubator_attach_result(result_body)
        self.assertTrue(self.service.incubator_attach_result(result_body)["duplicate"])
        restored = WorkflowService(self.data, recover_jobs=False)
        self.assertTrue(restored.incubator_attach_result(result_body)["duplicate"])
        self.assertEqual(len(restored.incubator_dispatches()["dispatches"]), 2)
        self.assertEqual(restored.incubator_list()["refinements"][0]["id"], published["refinement"]["id"])

    def test_current_user_edit_stops_followups_and_never_overwrites_new_body(self):
        published = self.publish()
        dispatch = self.claim()
        current = published["idea"]
        edited = self.service.incubator_update(request(id=current["id"], expectedRevision=current["revision"], body="用户手机新稿"))
        result = self.finish(dispatch)
        self.assertEqual(result["dispatch"]["status"], "needs_review")
        self.assertEqual(result["refinement"]["state"], "needs_review")
        self.assertEqual(result["idea"]["body"], edited["idea"]["body"])
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_editing_between_rounds_cancels_unsent_round_without_sending(self):
        self.publish()
        result = self.finish(self.claim())
        self.service.incubator_update(request(id=result["idea"]["id"], expectedRevision=result["idea"]["revision"], body="用户另改"))
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])
        self.assertEqual(self.service.incubator_list()["refinements"][0]["state"], "needs_review")
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "用户另改")

    def test_pause_sent_round_preserves_chat_receipt_but_does_not_apply_or_continue(self):
        published = self.publish()
        dispatch = self.claim()
        self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            targetThreadId=self.thread, status="waiting"))
        pause_body = request(id=published["refinement"]["id"])
        paused = workflow_post(self.service, "incubator/refinement/pause", pause_body)
        self.assertEqual(paused["refinement"]["state"], "paused")
        self.assertTrue(self.service.incubator_refinement_pause(pause_body)["duplicate"])
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "waiting")
        result = self.finish(dispatch)
        self.assertEqual(result["dispatch"]["status"], "completed")
        self.assertEqual(result["idea"]["body"], "用户原稿")
        self.assertEqual(result["refinement"]["state"], "paused")
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])

    def test_pause_unsent_round_cancels_it_and_keeps_source(self):
        published = self.publish()
        self.service.incubator_refinement_pause(request(id=published["refinement"]["id"]))
        self.assertEqual(self.service.incubator_dispatches()["dispatches"][0]["status"], "failed")
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "用户原稿")

    def test_missing_multiple_nested_or_empty_blocks_never_apply_body(self):
        for text in ("普通回答没有稿块", "<refined_prompt></refined_prompt>",
                     "<refined_prompt>一</refined_prompt><refined_prompt>二</refined_prompt>",
                     "<refined_prompt>外<refined_prompt>内</refined_prompt></refined_prompt>"):
            with self.subTest(text=text):
                isolated = WorkflowService(self.data / uuid.uuid4().hex)
                idea = isolated.incubator_create(request(title="边界", body="保留"))["idea"]
                published = isolated.incubator_publish(request(id=idea["id"], expectedRevision=1, targetKind="codex", purpose="refine"))
                dispatch = isolated.incubator_claim(request())["dispatch"]
                result = isolated.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
                    status="completed", targetThreadId=self.thread, result={"text": text, "turnId": "actual-turn"}))
                self.assertEqual(result["dispatch"]["status"], "needs_review")
                self.assertEqual(result["idea"]["body"], "保留")
                self.assertEqual(result["refinement"]["state"], "needs_review")
                self.assertEqual(len(isolated.incubator_dispatches()["dispatches"]), 1)

    def test_same_turn_and_ambiguous_delivery_rules_still_apply_to_refinement(self):
        self.publish()
        dispatch = self.claim()
        self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            targetThreadId=self.thread, result={"turnId": "actual", "sourceMessageId": "user-id"}))
        self.error(lambda: self.finish(dispatch), 409)
        self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], status="needs_review", error="发送是否成功不明"))
        self.error(lambda: self.service.incubator_claim(request()), 409)
        self.error(lambda: self.service.incubator_attach_result(request(id=dispatch["id"], claimToken=dispatch["claimToken"],
            targetThreadId=self.thread, status="waiting")), 409)
        self.assertEqual(self.service.incubator_list()["ideas"][0]["body"], "用户原稿")

    def test_pause_authorization_revoke_rolls_back_every_change(self):
        published = self.publish()
        before = self.service.incubator_list()
        calls = []
        def authorize():
            calls.append(True)
            if len(calls) == 2:
                raise WorkflowError("设备已撤销", 401)
        self.error(lambda: self.service.incubator_refinement_pause(request(id=published["refinement"]["id"]), authorize=authorize), 401)
        self.assertEqual(self.service.incubator_list(), before)

    def test_restart_unknown_delivery_does_not_auto_claim_another_round(self):
        self.publish()
        dispatch = self.claim()
        restarted = WorkflowService(self.data)
        self.assertEqual(restarted.incubator_dispatches(waiting=True, private=True)["dispatches"][0]["status"], "needs_review")
        self.error(lambda: restarted.incubator_claim(request()), 409)
        self.assertEqual(len(restarted.incubator_dispatches()["dispatches"]), 1)
        self.assertEqual(restarted.incubator_list()["ideas"][0]["body"], "用户原稿")
        self.assertEqual(restarted.incubator_dispatches(waiting=True, private=True)["dispatches"][0]["claimToken"], dispatch["claimToken"])

    def test_known_failed_refinement_stops_without_automatic_retry(self):
        self.publish()
        dispatch = self.claim()
        failed = self.service.incubator_fail(request(id=dispatch["id"], claimToken=dispatch["claimToken"], error="工具明确未接收"))
        self.assertEqual(failed["dispatch"]["status"], "failed")
        self.assertEqual(failed["refinement"]["state"], "paused")
        self.assertEqual(failed["idea"]["stage"], "thinking")
        self.assertEqual(failed["idea"]["body"], "用户原稿")
        self.assertIsNone(self.service.incubator_claim(request())["dispatch"])
        self.assertEqual(len(self.service.incubator_dispatches()["dispatches"]), 1)

    def test_pausing_old_session_cannot_change_new_session_or_its_draft_revision(self):
        older = self.publish()
        self.service.incubator_refinement_pause(request(id=older["refinement"]["id"]))
        self.idea = self.service.incubator_list()["ideas"][0]
        newer = self.publish(roundLimit=1)
        before = newer["idea"]
        self.service.incubator_refinement_pause(request(id=older["refinement"]["id"]))
        listed = self.service.incubator_list()
        self.assertEqual(listed["ideas"][0], before)
        self.assertEqual(next(item for item in listed["refinements"] if item["id"] == newer["refinement"]["id"])["state"], "active")
        self.assertEqual(self.finish(self.claim())["idea"]["stage"], "ready")


if __name__ == "__main__":
    unittest.main(verbosity=2)
