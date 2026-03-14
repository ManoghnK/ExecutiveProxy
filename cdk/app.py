#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.dynamo_stack import DynamoStack
from stacks.lambda_stack import LambdaStack
from stacks.appsync_stack import AppSyncStack

app = cdk.App()

env = cdk.Environment(region="us-east-1")

dynamo = DynamoStack(app, "ExecProxyDynamo", env=env)

lambdas = LambdaStack(
    app, 
    "ExecProxyLambdas", 
    env=env,
    meeting_table=dynamo.meeting_table,
    action_table=dynamo.action_table
)

appsync = AppSyncStack(
    app,
    "ExecProxyAppSync",
    env=env,
    meeting_table=dynamo.meeting_table,
    action_table=dynamo.action_table,
)

app.synth()

