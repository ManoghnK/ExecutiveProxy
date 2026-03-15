import boto3
import os

def test_dynamodb():
    print("Testing DynamoDB tables...")
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    try:
        meeting_table = dynamodb.describe_table(TableName='MeetingState')
        print(f"✅ MeetingState table status: {meeting_table['Table']['TableStatus']}")
        action_table = dynamodb.describe_table(TableName='ActionLog')
        print(f"✅ ActionLog table status: {action_table['Table']['TableStatus']}")
    except Exception as e:
        print(f"❌ DynamoDB Error: {e}")

def test_lambdas():
    print("\nTesting Lambda functions...")
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    try:
        functions = lambda_client.list_functions()
        expected = ['transcribehandler', 'classifier', 'executor', 'raghandler', 'streamresolver']
        found = []
        for func in functions['Functions']:
            if 'ExecProxy' in func['FunctionName']:
                found.append(func['FunctionName'])
                print(f"✅ Found function: {func['FunctionName']}")
        
        # Check if all expected types are present
        for exp in expected:
            if any(exp in f for f in found):
                print(f"✅ {exp} is deployed")
            else:
                print(f"❌ {exp} is MISSING")
    except Exception as e:
        print(f"❌ Lambda Error: {e}")

if __name__ == '__main__':
    test_dynamodb()
    test_lambdas()
