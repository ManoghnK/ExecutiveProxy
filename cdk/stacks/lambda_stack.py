from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as iam,
    Duration,
    CfnOutput,
    BundlingOptions,
)
from constructs import Construct

class LambdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 meeting_table, action_table, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── 1. Transcribe Handler (Nova 2 Sonic) ─────────────────────────────
        # Ingests audio stream, calls Bedrock Nova Sonic, writes transcript to DynamoDB,
        # then invokes classifier Lambda asynchronously.
        self.transcribe_function = _lambda.Function(
            self,
            "TranscribeHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(
                "../lambdas/transcribe_handler",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp -au . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.seconds(120),  # Streaming + DynamoDB + async invoke
            memory_size=512,  # Extra memory for audio processing
            environment={
                "DYNAMODB_MEETING_TABLE": meeting_table.table_name,
                "MODEL_ID": "amazon.nova-2-sonic-v1:0",
                # CLASSIFIER_LAMBDA_ARN set below after classifier is created
            },
        )
        # Permissions
        meeting_table.grant_write_data(self.transcribe_function)
        self.transcribe_function.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:InvokeModelWithBidirectionalStream",
            ],
            resources=["*"]  # Specific ARN preferred in prod but "*" ensures model access
        ))

        # ── 2. Classifier Handler (Nova 2 Lite) ──────────────────────────────
        # Reads transcript, determines intent (filter), updates MeetingState.
        self.classifier_function = _lambda.Function(
            self,
            "ClassifierHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("../lambdas/classifier"),
            timeout=Duration.seconds(30),
            environment={
                "MEETING_TABLE": meeting_table.table_name,
                "MODEL_ID": "amazon.nova-2-lite-v1:0",
            },
        )
        # Permissions
        meeting_table.grant_read_write_data(self.classifier_function)
        self.classifier_function.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"]
        ))

        # ── Wire: Transcribe → Classifier ────────────────────────────────────
        # Now that classifier exists, set the ARN and grant invoke permission
        self.transcribe_function.add_environment(
            "CLASSIFIER_LAMBDA_ARN", self.classifier_function.function_arn
        )
        self.classifier_function.grant_invoke(self.transcribe_function)

        # ── 3. RAG Handler (Pinecone) ────────────────────────────────────────
        # Helper for retrieving context. Invoked by Executor.
        self.rag_function = _lambda.Function(
            self,
            "RagHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("../lambdas/rag_handler"),
            timeout=Duration.seconds(30),
            environment={
                "PINECONE_INDEX_NAME": "executive-proxy-policies",
                # PINECONE_API_KEY to be added via Secrets Manager later
            },
        )
        # Permissions - Placeholder for Secrets Manager
        self.rag_function.add_to_role_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue", "s3:GetObject"],
            resources=["*"]
        ))

        # ── 4. Executor Handler (Nova Pro) ───────────────────────────────────
        # Orchestrates tools (Nova Act) + RAG to take action.
        self.executor_function = _lambda.Function(
            self,
            "ExecutorHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("../lambdas/executor"),
            timeout=Duration.seconds(120), # Long timeout for complex reasoning
            environment={
                "MEETING_TABLE": meeting_table.table_name,
                "ACTION_TABLE": action_table.table_name,
                "RAG_FUNCTION_NAME": self.rag_function.function_name,
                "MODEL_ID": "amazon.nova-pro-v1:0",
            },
        )
        # Permissions
        meeting_table.grant_read_data(self.executor_function)
        action_table.grant_write_data(self.executor_function)
        self.rag_function.grant_invoke(self.executor_function)
        self.executor_function.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"]
        ))

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(self, "TranscribeFunctionName", value=self.transcribe_function.function_name)
        CfnOutput(self, "ClassifierFunctionName", value=self.classifier_function.function_name)
        CfnOutput(self, "ExecutorFunctionName", value=self.executor_function.function_name)
        CfnOutput(self, "RagFunctionName", value=self.rag_function.function_name)
