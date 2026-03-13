from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct


class DynamoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── Table 1: MeetingState ──────────────────────────────────────────
        # Stores live transcript chunks + intent labels per meeting.
        # DynamoDB Stream feeds AppSync → Electron frontend in real-time.
        self.meeting_table = dynamodb.Table(
            self,
            "MeetingState",
            table_name="MeetingState",
            partition_key=dynamodb.Attribute(
                name="meeting_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            # TTL: auto-expire meeting records after 7 days (cost control)
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,  # safe for hackathon; change for prod
        )

        # ── Table 2: ActionLog ────────────────────────────────────────────
        # Records every agent action (Jira ticket, Calendar event, Risk Matrix).
        # Frontend polls/subscribes to show execution status cards.
        self.action_table = dynamodb.Table(
            self,
            "ActionLog",
            table_name="ActionLog",
            partition_key=dynamodb.Attribute(
                name="meeting_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="action_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # GSI: query all actions by type across meetings (useful for demo)
        self.action_table.add_global_secondary_index(
            index_name="ActionTypeIndex",
            partition_key=dynamodb.Attribute(
                name="action_type",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Outputs (referenced by Lambda stack) ──────────────────────────
        CfnOutput(self, "MeetingTableName", value=self.meeting_table.table_name)
        CfnOutput(self, "MeetingTableArn", value=self.meeting_table.table_arn)
        CfnOutput(
            self,
            "MeetingTableStreamArn",
            value=self.meeting_table.table_stream_arn or "no-stream",
        )
        CfnOutput(self, "ActionTableName", value=self.action_table.table_name)
        CfnOutput(self, "ActionTableArn", value=self.action_table.table_arn)
        CfnOutput(
            self,
            "ActionTableStreamArn",
            value=self.action_table.table_stream_arn or "no-stream",
        )
