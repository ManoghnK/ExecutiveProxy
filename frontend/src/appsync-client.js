import { Amplify } from 'https://esm.sh/aws-amplify@6?bundle';
import { generateClient } from 'https://esm.sh/aws-amplify@6/api?bundle';

let client = null;
let subscription = null;

export const configureAppSync = (config) => {
    Amplify.configure({
        API: {
            GraphQL: {
                endpoint: config.appSyncUrl,
                region: 'us-east-1',
                defaultAuthMode: 'apiKey',
                apiKey: config.appSyncKey
            }
        }
    });
    client = generateClient();
};

export const subscribeToMeeting = (meetingId, onTranscript, onAction) => {
    if (!client) return;

    // Subscription for Transcript Updates
    const transcriptSub = client.graphql({
        query: `
            subscription OnMeetingUpdate($meeting_id: String!) {
                onMeetingUpdate(meeting_id: $meeting_id) {
                    meeting_id
                    timestamp
                    speaker
                    transcript_chunk
                    intent_label
                    action_triggered
                }
            }
        `,
        variables: { meeting_id: meetingId }
    }).subscribe({
        next: ({ data }) => {
            if (data.onMeetingUpdate) {
                onTranscript(data.onMeetingUpdate);
            }
        },
        error: (error) => console.error('Transcript subscription error:', error)
    });

    // Subscription for Action Logs
    const actionSub = client.graphql({
        query: `
            subscription OnActionLog($meeting_id: String!) {
                onActionLog(meeting_id: $meeting_id) {
                    meeting_id
                    action_id
                    action_type
                    status
                    payload
                    result
                    created_at
                }
            }
        `,
        variables: { meeting_id: meetingId }
    }).subscribe({
        next: ({ data }) => {
            if (data.onActionLog) {
                onAction(data.onActionLog);
            }
        },
        error: (error) => console.error('Action subscription error:', error)
    });

    return () => {
        transcriptSub.unsubscribe();
        actionSub.unsubscribe();
    };
};
