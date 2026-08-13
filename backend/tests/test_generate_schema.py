"""GenerateRequest / JobStatusResponse schema tests (Phase 2.3-A)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pydantic import ValidationError  # noqa: E402

from backend.app.schemas.character import GenerateRequest, JobStatusResponse  # noqa: E402

MIN_SPEC = {
    "id": "s1",
    "name": "测试角色",
    "style": "stylized",
    "gender": "female",
    "heightCm": 160,
    "description": "",
    "referenceImageIds": [],
    "tags": [],
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}


class GenerateRequestSchemaTest(unittest.TestCase):
    def test_old_request_compatible(self):
        # No references / timeoutSeconds -> defaults, fully backward compatible.
        req = GenerateRequest(provider="mock", spec=MIN_SPEC)
        self.assertEqual(req.references, [])
        self.assertIsNone(req.timeout_seconds)
        self.assertEqual(req.reference_image_ids, [])

    def test_with_references_and_timeout(self):
        req = GenerateRequest(
            provider="mock",
            spec=MIN_SPEC,
            timeoutSeconds=60,
            references=[
                {"imageId": "a", "dataUrl": "data:image/png;base64,AA", "view": "front"},
                {"imageId": "b", "dataUrl": "data:image/png;base64,BB", "view": "side"},
            ],
        )
        self.assertEqual(req.timeout_seconds, 60)
        self.assertEqual(len(req.references), 2)
        self.assertEqual(req.references[0].view, "front")

    def test_references_limit_rejects_over_4(self):
        refs = [{"imageId": f"i{i}", "dataUrl": "data:image/png;base64,AA", "view": "front"} for i in range(5)]
        with self.assertRaises(ValidationError):
            GenerateRequest(provider="mock", spec=MIN_SPEC, references=refs)

    def test_job_status_response_fields(self):
        resp = JobStatusResponse(
            jobId="j1",
            status="timed_out",
            progress=0.5,
            message="生成超时",
            steps=[],
            error="生成超时",
            deadlineAt=123.0,
            durationMs=1500,
            retryable=True,
            cancelledByUser=False,
            timedOut=True,
            attempt=2,
        )
        self.assertEqual(resp.status, "timed_out")
        self.assertTrue(resp.timed_out)
        self.assertTrue(resp.retryable)
        self.assertEqual(resp.attempt, 2)
        self.assertEqual(resp.duration_ms, 1500)

    def test_cancelled_status_is_valid(self):
        resp = JobStatusResponse(jobId="j2", status="cancelled", progress=0.0, message="已取消", steps=[])
        self.assertEqual(resp.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
