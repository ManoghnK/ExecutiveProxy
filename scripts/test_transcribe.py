"""
Test script for transcribe_handler Lambda.

Usage:
  # Test with synthetic audio against deployed Lambda:
  python scripts/test_transcribe.py

  # Test with a real WAV file:
  python scripts/test_transcribe.py --wav path/to/audio.wav

  # Test local handler (no Lambda invoke):
  python scripts/test_transcribe.py --local
"""

import argparse
import base64
import json
import math
import struct
import sys
import uuid
import wave

import boto3


# ── Config ───────────────────────────────────────────────────────────────────
REGION = "us-east-1"
SAMPLE_RATE = 16000  # 16 kHz
CHANNELS = 1
SAMPLE_WIDTH = 2     # 16-bit


def generate_synthetic_audio(duration_s: float = 3.0, frequency: float = 440.0) -> bytes:
    """Generate a sine wave as raw 16kHz 16-bit PCM audio."""
    num_samples = int(SAMPLE_RATE * duration_s)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
        samples.append(struct.pack("<h", sample))
    raw = b"".join(samples)
    print(f"  Generated {len(raw):,} bytes ({duration_s}s @ {SAMPLE_RATE}Hz, {frequency}Hz tone)")
    return raw


def load_wav_file(path: str) -> bytes:
    """Load a WAV file and return raw PCM bytes. Warns if format differs."""
    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

        if rate != SAMPLE_RATE:
            print(f"  WARNING: WAV sample rate is {rate}Hz (expected {SAMPLE_RATE}Hz)")
        if channels != 1:
            print(f"  WARNING: WAV has {channels} channels (expected mono)")
        if width != 2:
            print(f"  WARNING: WAV sample width is {width} bytes (expected 2)")

        duration = len(frames) / (rate * channels * width)
        print(f"  Loaded {path}: {len(frames):,} bytes, ~{duration:.1f}s")
        return frames


def get_lambda_function_name() -> str:
    """Look up the transcribe function name from CloudFormation outputs."""
    cf = boto3.client("cloudformation", region_name=REGION)
    try:
        resp = cf.describe_stacks(StackName="ExecProxyLambdas")
        outputs = resp["Stacks"][0].get("Outputs", [])
        for out in outputs:
            if out["OutputKey"] == "TranscribeFunctionName":
                return out["OutputValue"]
    except Exception as e:
        print(f"  Could not look up stack outputs: {e}")

    # Fallback: ask user
    return input("  Enter transcribe Lambda function name: ").strip()


def invoke_lambda(function_name: str, audio_bytes: bytes, meeting_id: str) -> dict:
    """Invoke the deployed Lambda with audio payload."""
    client = boto3.client("lambda", region_name=REGION)

    payload = {
        "meeting_id": meeting_id,
        "audio_bytes": base64.b64encode(audio_bytes).decode("utf-8"),
        "speaker": "test-speaker",
    }

    print(f"  Invoking {function_name} ({len(audio_bytes):,} bytes audio)...")
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )

    response_payload = json.loads(response["Payload"].read().decode("utf-8"))
    return response_payload


def run_local_test(audio_bytes: bytes, meeting_id: str) -> dict:
    """Run the handler locally (imports handler.py directly)."""
    sys.path.insert(0, "lambdas/transcribe_handler")
    from handler import handler

    event = {
        "meeting_id": meeting_id,
        "audio_bytes": base64.b64encode(audio_bytes).decode("utf-8"),
        "speaker": "local-test-speaker",
    }
    return handler(event, None)


def main():
    parser = argparse.ArgumentParser(description="Test transcribe_handler Lambda")
    parser.add_argument("--wav", help="Path to a WAV file to use as input")
    parser.add_argument("--local", action="store_true", help="Run handler locally instead of Lambda")
    parser.add_argument("--duration", type=float, default=3.0, help="Duration of synthetic audio (seconds)")
    args = parser.parse_args()

    print("=" * 60)
    print("transcribe_handler — Integration Test")
    print("=" * 60)

    # 1. Prepare audio
    print("\n[1/3] Preparing audio...")
    if args.wav:
        audio_bytes = load_wav_file(args.wav)
    else:
        audio_bytes = generate_synthetic_audio(args.duration)

    meeting_id = f"test-{uuid.uuid4()}"
    print(f"  Meeting ID: {meeting_id}")

    # 2. Invoke
    print("\n[2/3] Invoking handler...")
    if args.local:
        print("  Mode: LOCAL")
        result = run_local_test(audio_bytes, meeting_id)
    else:
        print("  Mode: DEPLOYED LAMBDA")
        function_name = get_lambda_function_name()
        print(f"  Function: {function_name}")
        result = invoke_lambda(function_name, audio_bytes, meeting_id)

    # 3. Validate
    print("\n[3/3] Results:")
    print(json.dumps(result, indent=2))

    # Assertions
    print("\n--- Validation ---")
    status_code = result.get("statusCode", 0)
    body = result.get("body", "{}")
    if isinstance(body, str):
        body = json.loads(body)

    checks = {
        "statusCode == 200": status_code == 200,
        "transcript present": bool(body.get("transcript")),
        "meeting_id matches": body.get("meeting_id") == meeting_id,
        "dynamo_write": body.get("dynamo_write", False),
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")
        if not passed:
            all_pass = False

    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
