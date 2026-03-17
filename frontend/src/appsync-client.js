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
            subscription SubscribeToMeeting($meeting_id: ID!) {
                subscribeToMeeting(meeting_id: $meeting_id) {
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
            if (data.subscribeToMeeting) {
                onTranscript(data.subscribeToMeeting);
            }
        },
        error: (error) => console.error('Transcript subscription error:', error)
    });

    // Subscription for Action Logs
    const actionSub = client.graphql({
        query: `
            subscription SubscribeToActions($meeting_id: ID!) {
                subscribeToActions(meeting_id: $meeting_id) {
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
            if (data.subscribeToActions) {
                onAction(data.subscribeToActions);
            }
        },
        error: (error) => console.error('Action subscription error:', error)
    });

    return () => {
        transcriptSub.unsubscribe();
        actionSub.unsubscribe();
    };
};
