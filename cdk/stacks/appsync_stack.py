from aws_cdk import (
    Stack,
    aws_appsync as appsync,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_lambda_event_sources as event_sources,
    aws_iam as iam,
    Duration,
    Expiration,
    CfnOutput,
)
from constructs import Construct
import os


class AppSyncStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        meeting_table: dynamodb.ITable,
        action_table: dynamodb.ITable,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # ── 1. AppSync GraphQL API ───────────────────────────────────────────
        self.api = appsync.GraphqlApi(
            self,
            "ExecProxyApi",
            name="ExecProxyGraphQL",
            definition=appsync.Definition.from_file(
                os.path.join(os.path.dirname(__file__), "..", "schema.graphql")
            ),
            authorization_config=appsync.AuthorizationConfig(
                default_authorization=appsync.AuthorizationMode(
                    authorization_type=appsync.AuthorizationType.API_KEY,
                    api_key_config=appsync.ApiKeyConfig(
                        name="ExecProxyApiKey",
                        description="Executive Proxy hackathon API key",
                        expires=Expiration.after(Duration.days(365)),
                    ),
                )
            ),
            log_config=appsync.LogConfig(
                field_log_level=appsync.FieldLogLevel.ALL,
            ),
            xray_enabled=True,
        )

        # ── 2. DynamoDB Data Sources ─────────────────────────────────────────
        meeting_ds = self.api.add_dynamo_db_data_source(
            "MeetingStateDS", meeting_table
        )
        action_ds = self.api.add_dynamo_db_data_source(
            "ActionLogDS", action_table
        )

        # ── 3. Query Resolvers (DynamoDB direct) ─────────────────────────────

        # getMeeting — query MeetingState by meeting_id
        meeting_ds.create_resolver(
            "GetMeetingResolver",
            type_name="Query",
            field_name="getMeeting",
            request_mapping_template=appsync.MappingTemplate.from_string(
                """{
                    "version": "2017-02-28",
                    "operation": "Query",
                    "query": {
                        "expression": "meeting_id = :mid",
                        "expressionValues": {
                            ":mid": $util.dynamodb.toDynamoDBJson($ctx.args.meeting_id)
                        }
                    },
                    "scanIndexForward": false,
                    "limit": 100
                }"""
            ),
            response_mapping_template=appsync.MappingTemplate.from_string(
                """{"items": $util.toJson($ctx.result.items)}"""
            ),
        )

        # getActions — query ActionLog by meeting_id
        action_ds.create_resolver(
            "GetActionsResolver",
            type_name="Query",
            field_name="getActions",
            request_mapping_template=appsync.MappingTemplate.from_string(
                """{
                    "version": "2017-02-28",
                    "operation": "Query",
                    "query": {
                        "expression": "meeting_id = :mid",
                        "expressionValues": {
                            ":mid": $util.dynamodb.toDynamoDBJson($ctx.args.meeting_id)
                        }
                    },
                    "scanIndexForward": false,
                    "limit": 50
                }"""
            ),
            response_mapping_template=appsync.MappingTemplate.from_string(
                """{"items": $util.toJson($ctx.result.items)}"""
            ),
        )

        # ── 4. Mutation Resolvers (None/Local — just pass through for subs) ──
        none_ds = self.api.add_none_data_source("NoneDS")

        # onTranscriptUpdate — passthrough for subscriptions
        none_ds.create_resolver(
            "OnTranscriptUpdateResolver",
            type_name="Mutation",
            field_name="onTranscriptUpdate",
            request_mapping_template=appsync.MappingTemplate.from_string(
                """{
                    "version": "2017-02-28",
                    "payload": {
                        "meeting_id": "$ctx.args.meeting_id",
                        "timestamp": "$ctx.args.timestamp",
                        "speaker": "$util.defaultIfNullOrEmpty($ctx.args.speaker, "")",
                        "transcript_chunk": "$util.defaultIfNullOrEmpty($ctx.args.transcript_chunk, "")",
                        "intent_label": "$util.defaultIfNullOrEmpty($ctx.args.intent_label, "")",
                        "action_triggered": $util.defaultIfNull($ctx.args.action_triggered, false)
                    }
                }"""
            ),
            response_mapping_template=appsync.MappingTemplate.from_string(
                """$util.toJson($ctx.result)"""
            ),
        )

        # onActionComplete — passthrough for subscriptions
        none_ds.create_resolver(
            "OnActionCompleteResolver",
            type_name="Mutation",
            field_name="onActionComplete",
            request_mapping_template=appsync.MappingTemplate.from_string(
                """{
                    "version": "2017-02-28",
                    "payload": {
                        "meeting_id": "$ctx.args.meeting_id",
                        "action_id": "$ctx.args.action_id",
                        "action_type": "$ctx.args.action_type",
                        "status": "$ctx.args.status",
                        "payload": "$util.defaultIfNullOrEmpty($ctx.args.payload, "")",
                        "result": "$util.defaultIfNullOrEmpty($ctx.args.result, "")",
                        "created_at": "$ctx.args.created_at"
                    }
                }"""
            ),
            response_mapping_template=appsync.MappingTemplate.from_string(
                """$util.toJson($ctx.result)"""
            ),
        )

        # ── 5. Stream Resolver Lambda ────────────────────────────────────────
        self.stream_resolver = _lambda.Function(
            self,
            "StreamResolver",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("../lambdas/stream_resolver"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "APPSYNC_API_URL": self.api.graphql_url,
                "APPSYNC_API_KEY": self.api.api_key or "",
            },
        )

        # Grant Lambda permission to call AppSync mutations
        self.stream_resolver.add_to_role_policy(
            iam.PolicyStatement(
                actions=["appsync:GraphQL"],
                resources=[
                    f"{self.api.arn}/types/Mutation/*",
                ],
            )
        )

        # ── 6. DynamoDB Stream → Lambda Event Source Mappings ────────────────
        # MeetingState stream
        self.stream_resolver.add_event_source(
            event_sources.DynamoEventSource(
                meeting_table,
                starting_position=_lambda.StartingPosition.LATEST,
                batch_size=10,
                retry_attempts=3,
                bisect_batch_on_error=True,
            )
        )

        # ActionLog stream
        self.stream_resolver.add_event_source(
            event_sources.DynamoEventSource(
                action_table,
                starting_position=_lambda.StartingPosition.LATEST,
                batch_size=10,
                retry_attempts=3,
                bisect_batch_on_error=True,
            )
        )

        # ── 7. Outputs ──────────────────────────────────────────────────────
        CfnOutput(
            self, "AppSyncApiUrl",
            value=self.api.graphql_url,
            description="AppSync GraphQL endpoint URL",
        )
        CfnOutput(
            self, "AppSyncApiKey",
            value=self.api.api_key or "check-console",
            description="AppSync API key for frontend",
        )
        CfnOutput(
            self, "AppSyncApiId",
            value=self.api.api_id,
            description="AppSync API ID",
        )
