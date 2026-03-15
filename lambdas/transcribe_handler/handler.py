"""
transcribe_handler — Nova 2 Sonic Voice Ingestion Lambda

Permissions required:
- bedrock:InvokeModelWithBidirectionalStream (amazon.nova-2-sonic-v1:0)
- dynamodb:PutItem (MeetingState)
- lambda:InvokeFunction (classifier Lambda)

Flow:
  Audio bytes (base64) → Nova 2 Sonic bidirectional stream → ASR text
  → DynamoDB MeetingState → async classifier invocation
"""

import os
import json
import uuid
import base64
import asyncio
import logging
import datetime
from typing import Optional

import boto3

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Config ───────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_MEETING_TABLE = os.environ.get("DYNAMODB_MEETING_TABLE", "MeetingState")
CLASSIFIER_LAMBDA_ARN = os.environ.get("CLASSIFIER_LAMBDA_ARN", "")
MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-2-sonic-v1:0")

# Audio config
SAMPLE_RATE = 16000       # 16 kHz PCM
AUDIO_CHUNK_SIZE = 1024   # Bytes per streaming chunk sent to Nova Sonic
AUDIO_CONTENT_TYPE = "audio/lpcm"
AUDIO_MEDIA_TYPE = "audio/lpcm"

# ── AWS Clients ──────────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)


# ── Nova Sonic Bidirectional Streaming ───────────────────────────────────────

async def transcribe_audio_nova_sonic(audio_bytes: bytes) -> str:
    """
    Send audio to Nova 2 Sonic via bidirectional streaming and extract
    the ASR (speech-to-text) transcription from the response events.

    Uses the aws_sdk_bedrock_runtime package for InvokeModelWithBidirectionalStream.
    """
    try:
        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
        from aws_sdk_bedrock_runtime.config import Config, HTTPConfig
        from aws_sdk_bedrock_runtime.models import (
            InvokeModelWithBidirectionalStreamOperationInput,
            BidirectionalInputPayloadStream,
        )
    except ImportError:
        logger.warning(
            "aws_sdk_bedrock_runtime not available. "
            "Falling back to simulated transcription."
        )
        return _fallback_transcription(audio_bytes)

    config = Config(
        endpoint_url=f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com",
        region=AWS_REGION,
        http=HTTPConfig(connect_timeout=10, read_timeout=120),
    )
    client = BedrockRuntimeClient(config=config)

    # Build the session configuration event
    session_id = str(uuid.uuid4())
    session_config = {
        "event": {
            "sessionConfiguration": {
                "inferenceConfiguration": {
                    "maxTokens": 1024,
                    "temperature": 0.0,
                },
                "audioInputConfiguration": {
                    "mediaType": AUDIO_MEDIA_TYPE,
                    "sampleRateHertz": SAMPLE_RATE,
                    "singleUtterance": True,
                },
                "audioOutputConfiguration": {
                    "mediaType": AUDIO_MEDIA_TYPE,
                    "sampleRateHertz": SAMPLE_RATE,
                },
                "systemPrompt": (
                    "You are a transcription assistant. "
                    "Listen to the audio and provide an accurate text transcription. "
                    "Output only the transcribed text."
                ),
                "sessionId": session_id,
            }
        }
    }

    transcript_parts: list[str] = []

    try:
        # Create the bidirectional stream
        async def input_stream():
            """Generator that yields events to Nova Sonic."""
            # 1. Send session configuration
            yield BidirectionalInputPayloadStream(
                chunk=json.dumps(session_config).encode("utf-8")
            )

            # 2. Stream audio in chunks
            for offset in range(0, len(audio_bytes), AUDIO_CHUNK_SIZE):
                chunk = audio_bytes[offset : offset + AUDIO_CHUNK_SIZE]
                audio_event = {
                    "event": {
                        "audioInput": {
                            "audio": base64.b64encode(chunk).decode("utf-8"),
                            "contentType": AUDIO_CONTENT_TYPE,
                        }
                    }
                }
                yield BidirectionalInputPayloadStream(
                    chunk=json.dumps(audio_event).encode("utf-8")
                )
                await asyncio.sleep(0)  # Yield control

            # 3. Signal end of audio
            end_event = {
                "event": {
                    "audioStreamComplete": {}
                }
            }
            yield BidirectionalInputPayloadStream(
                chunk=json.dumps(end_event).encode("utf-8")
            )

        # Invoke the bidirectional stream
        response = await client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(
                model_id=MODEL_ID,
                body=input_stream(),
            )
        )

        # Process response events
        async for event in response.body:
            try:
                payload = json.loads(event.chunk.decode("utf-8"))

                # Extract ASR transcription text
                if "event" in payload:
                    evt = payload["event"]

                    # Text output from ASR
                    if "textOutput" in evt:
                        text = evt["textOutput"].get("text", "")
                        if text.strip():
                            transcript_parts.append(text.strip())
                            logger.info(f"ASR partial: {text.strip()}")

                    # Content block with text (alternative format)
                    if "contentBlockDelta" in evt:
                        delta = evt["contentBlockDelta"].get("delta", {})
                        if "text" in delta:
                            transcript_parts.append(delta["text"])

            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Skipping malformed event: {e}")
                continue

    except Exception as e:
        logger.error(f"Nova Sonic streaming error: {e}", exc_info=True)
        if not transcript_parts:
            return _fallback_transcription(audio_bytes)

    full_transcript = " ".join(transcript_parts).strip()

    if not full_transcript:
        logger.warning("Nova Sonic returned empty transcription. Using fallback.")
        return _fallback_transcription(audio_bytes)

    logger.info(f"Transcription complete: {full_transcript[:100]}...")
    return full_transcript


def _fallback_transcription(audio_bytes: bytes) -> str:
    """
    Fallback: use standard boto3 Bedrock converse API to describe audio.
    This is a safety net if the bidirectional SDK is unavailable or errors out.
    In production, this would not produce real transcription from raw audio —
    it returns a marker indicating the fallback was used, along with audio metadata.
    """
    audio_size_kb = len(audio_bytes) / 1024
    duration_est = len(audio_bytes) / (SAMPLE_RATE * 2)  # 16-bit PCM = 2 bytes/sample
    logger.info(
        f"Fallback transcription: {audio_size_kb:.1f} KB audio, "
        f"~{duration_est:.1f}s estimated duration"
    )
    return (
        f"[FALLBACK] Audio received: {audio_size_kb:.1f} KB, "
        f"~{duration_est:.1f}s. Nova Sonic SDK unavailable — "
        f"deploy with requirements.txt to enable real transcription."
    )


# ── DynamoDB Write ───────────────────────────────────────────────────────────

def write_transcript_to_dynamo(
    meeting_id: str,
    timestamp: str,
    speaker: str,
    transcript_chunk: str,
) -> bool:
    """Write a transcript chunk to the MeetingState DynamoDB table."""
    try:
        table = dynamodb.Table(DYNAMODB_MEETING_TABLE)
        item = {
            "meeting_id": meeting_id,
            "timestamp": timestamp,
            "speaker": speaker,
            "transcript_chunk": transcript_chunk,
            "intent_label": None,           # Set later by classifier
            "action_triggered": False,       # Set later by classifier
        }
        table.put_item(Item=item)
        logger.info(
            f"DynamoDB write OK: meeting={meeting_id}, "
            f"ts={timestamp}, len={len(transcript_chunk)}"
        )
        return True
    except Exception as e:
        logger.error(f"DynamoDB write failed: {e}", exc_info=True)
        return False


# ── Classifier Invocation ────────────────────────────────────────────────────

def invoke_classifier(
    meeting_id: str,
    speaker: str,
    transcript_chunk: str,
    timestamp: str,
) -> bool:
    """Invoke the classifier Lambda asynchronously with the transcript chunk."""
    if not CLASSIFIER_LAMBDA_ARN:
        logger.warning("CLASSIFIER_LAMBDA_ARN not set. Skipping classifier invocation.")
        return False

    payload = {
        "meeting_id": meeting_id,
        "speaker": speaker,
        "transcript_chunk": transcript_chunk,
        "timestamp": timestamp,
    }

    try:
        response = lambda_client.invoke(
            FunctionName=CLASSIFIER_LAMBDA_ARN,
            InvocationType="Event",  # Asynchronous — fire and forget
            Payload=json.dumps(payload),
        )
        status_code = response.get("StatusCode", 0)
        logger.info(
            f"Classifier invoked (async): ARN={CLASSIFIER_LAMBDA_ARN}, "
            f"status={status_code}"
        )
        return status_code == 202  # 202 = accepted for async
    except Exception as e:
        logger.error(f"Classifier invocation failed: {e}", exc_info=True)
        return False


# ── Lambda Entry Point ───────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """
    Lambda handler for Nova 2 Sonic voice ingestion.

    Event schema:
    {
        "meeting_id": "uuid-string",          # Required
        "audio_bytes": "base64-encoded-pcm",  # Required — 16kHz 16-bit PCM
        "speaker": "string",                  # Optional, default "unknown"
        "timestamp": "ISO8601"                # Optional, auto-generated if missing
    }

    Returns:
    {
        "statusCode": 200,
        "body": {
            "meeting_id": str,
            "timestamp": str,
            "transcript": str,
            "dynamo_write": bool,
            "classifier_invoked": bool
        }
    }
    """
    logger.info(f"transcribe_handler invoked. Event keys: {list(event.keys())}")

    # ── 1. Parse Input ───────────────────────────────────────────────────────
    meeting_id = event.get("meeting_id")
    if not meeting_id:
        logger.error("Missing required field: meeting_id")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "meeting_id is required"}),
        }

    audio_b64 = event.get("audio_bytes")
    if not audio_b64:
        logger.error("Missing required field: audio_bytes")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "audio_bytes (base64 PCM) is required"}),
        }

    speaker = event.get("speaker", "unknown")
    timestamp = event.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())

    # Decode audio
    try:
        audio_bytes = base64.b64decode(audio_b64)
        audio_duration_s = len(audio_bytes) / (SAMPLE_RATE * 2)  # 16-bit = 2 bytes/sample
        logger.info(
            f"Audio decoded: {len(audio_bytes)} bytes, "
            f"~{audio_duration_s:.1f}s, meeting={meeting_id}"
        )
    except Exception as e:
        logger.error(f"Failed to decode audio_bytes: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid base64 audio: {str(e)}"}),
        }

    # Validate minimum audio length (~1 second)
    min_bytes = SAMPLE_RATE * 2 * 1  # 1 second of 16kHz 16-bit PCM
    if len(audio_bytes) < min_bytes:
        logger.warning(
            f"Audio too short: {len(audio_bytes)} bytes "
            f"(minimum {min_bytes} for ~1s). Processing anyway."
        )

    # ── 2. Transcribe via Nova 2 Sonic ───────────────────────────────────────
    try:
        transcript = asyncio.get_event_loop().run_until_complete(
            transcribe_audio_nova_sonic(audio_bytes)
        )
    except RuntimeError:
        # If no event loop exists (varies by Lambda runtime version)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            transcript = loop.run_until_complete(
                transcribe_audio_nova_sonic(audio_bytes)
            )
        finally:
            loop.close()

    logger.info(f"Transcript result: {transcript[:200]}")

    # ── 3. Write to DynamoDB ─────────────────────────────────────────────────
    dynamo_ok = write_transcript_to_dynamo(
        meeting_id=meeting_id,
        timestamp=timestamp,
        speaker=speaker,
        transcript_chunk=transcript,
    )

    # ── 4. Invoke Classifier (async) ─────────────────────────────────────────
    classifier_ok = False
    if dynamo_ok and transcript and not transcript.startswith("[FALLBACK]"):
        classifier_ok = invoke_classifier(
            meeting_id=meeting_id,
            speaker=speaker,
            transcript_chunk=transcript,
            timestamp=timestamp,
        )
    else:
        logger.info("Skipping classifier: DynamoDB write failed or fallback transcript.")

    # ── 5. Return ────────────────────────────────────────────────────────────
    result = {
        "meeting_id": meeting_id,
        "timestamp": timestamp,
        "transcript": transcript,
        "speaker": speaker,
        "audio_duration_seconds": round(len(audio_bytes) / (SAMPLE_RATE * 2), 2),
        "dynamo_write": dynamo_ok,
        "classifier_invoked": classifier_ok,
    }

    logger.info(f"transcribe_handler complete: {json.dumps(result)}")

    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }


# ── Local Testing ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import struct
    import math

    print("=" * 60)
    print("transcribe_handler — Local Test")
    print("=" * 60)

    # Generate synthetic PCM audio (440 Hz sine wave, 3 seconds, 16kHz 16-bit)
    duration = 3.0
    frequency = 440.0
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
        samples.append(struct.pack("<h", sample))

    raw_audio = b"".join(samples)
    audio_b64 = base64.b64encode(raw_audio).decode("utf-8")

    print(f"Generated {len(raw_audio)} bytes of test audio ({duration}s @ {SAMPLE_RATE}Hz)")

    test_event = {
        "meeting_id": f"test-{uuid.uuid4()}",
        "audio_bytes": audio_b64,
        "speaker": "test-user",
    }

    result = handler(test_event, None)
    print(f"\nResult: {json.dumps(json.loads(result['body']), indent=2)}")
