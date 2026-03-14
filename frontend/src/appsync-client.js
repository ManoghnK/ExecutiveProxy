/**
 * AppSync Client for Executive Proxy Frontend.
 *
 * Connects to the AppSync GraphQL API for real-time meeting updates
 * via WebSocket subscriptions.
 *
 * Usage:
 *   import { createAppSyncClient, subscribeMeeting, subscribeActions } from './appsync-client';
 *   const client = createAppSyncClient();
 *   subscribeMeeting(client, meetingId, (data) => { ... });
 *   subscribeActions(client, meetingId, (data) => { ... });
 *
 * Requirements:
 *   npm install graphql-ws graphql
 *
 * Environment:
 *   REACT_APP_APPSYNC_URL  — from CDK output: AppSyncApiUrl
 *   REACT_APP_APPSYNC_KEY  — from CDK output: AppSyncApiKey
 */

// ── Config ──────────────────────────────────────────────────────────────────

const APPSYNC_URL = process.env.REACT_APP_APPSYNC_URL || '';
const APPSYNC_KEY = process.env.REACT_APP_APPSYNC_KEY || '';

// Convert HTTPS URL to WSS for subscriptions
const APPSYNC_REALTIME_URL = APPSYNC_URL
  .replace('https://', 'wss://')
  .replace('/graphql', '/graphql/realtime');


// ── GraphQL Operations ──────────────────────────────────────────────────────

export const GET_MEETING = `
  query GetMeeting($meeting_id: ID!) {
    getMeeting(meeting_id: $meeting_id) {
      items {
        meeting_id
        timestamp
        speaker
        transcript_chunk
        intent_label
        action_triggered
      }
    }
  }
`;

export const GET_ACTIONS = `
  query GetActions($meeting_id: ID!) {
    getActions(meeting_id: $meeting_id) {
      items {
        meeting_id
        action_id
        action_type
        status
        payload
        result
        created_at
      }
    }
  }
`;

export const SUBSCRIBE_MEETING = `
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
`;

export const SUBSCRIBE_ACTIONS = `
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
`;


// ── HTTP Query Helper ───────────────────────────────────────────────────────

export async function executeQuery(query, variables = {}) {
  const response = await fetch(APPSYNC_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': APPSYNC_KEY,
    },
    body: JSON.stringify({ query, variables }),
  });

  const result = await response.json();
  if (result.errors) {
    console.error('GraphQL errors:', result.errors);
    throw new Error(result.errors[0].message);
  }
  return result.data;
}


// ── Subscription Helper (AppSync Real-time WebSocket) ───────────────────────

/**
 * Subscribe to an AppSync subscription using the AppSync real-time protocol.
 * Returns an unsubscribe function.
 *
 * @param {string} query - GraphQL subscription query
 * @param {object} variables - Query variables
 * @param {function} onData - Callback for each received event
 * @param {function} onError - Callback for errors
 * @returns {function} unsubscribe function
 */
export function subscribe(query, variables, onData, onError) {
  // AppSync real-time requires base64 encoded auth header
  const header = btoa(JSON.stringify({
    host: new URL(APPSYNC_URL).host,
    'x-api-key': APPSYNC_KEY,
  }));
  const payload = btoa(JSON.stringify({}));

  const wsUrl = `${APPSYNC_REALTIME_URL}?header=${header}&payload=${payload}`;
  const ws = new WebSocket(wsUrl, ['graphql-ws']);

  let subscriptionId = null;

  ws.onopen = () => {
    // Send connection init
    ws.send(JSON.stringify({ type: 'connection_init' }));
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    switch (message.type) {
      case 'connection_ack':
        // Connection established, register subscription
        subscriptionId = crypto.randomUUID();
        ws.send(JSON.stringify({
          id: subscriptionId,
          type: 'start',
          payload: {
            data: JSON.stringify({ query, variables }),
            extensions: {
              authorization: {
                host: new URL(APPSYNC_URL).host,
                'x-api-key': APPSYNC_KEY,
              },
            },
          },
        }));
        break;

      case 'data':
        if (message.payload?.data) {
          const key = Object.keys(message.payload.data)[0];
          onData(message.payload.data[key]);
        }
        break;

      case 'error':
        console.error('Subscription error:', message.payload);
        if (onError) onError(message.payload);
        break;

      case 'ka':
        // Keep-alive, ignore
        break;
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    if (onError) onError(error);
  };

  // Return unsubscribe function
  return () => {
    if (subscriptionId) {
      ws.send(JSON.stringify({ id: subscriptionId, type: 'stop' }));
    }
    ws.close();
  };
}


// ── Convenience Functions ───────────────────────────────────────────────────

/**
 * Subscribe to real-time transcript updates for a meeting.
 * @returns {function} unsubscribe function
 */
export function subscribeMeeting(meetingId, onData, onError) {
  return subscribe(SUBSCRIBE_MEETING, { meeting_id: meetingId }, onData, onError);
}

/**
 * Subscribe to real-time action updates for a meeting.
 * @returns {function} unsubscribe function
 */
export function subscribeActions(meetingId, onData, onError) {
  return subscribe(SUBSCRIBE_ACTIONS, { meeting_id: meetingId }, onData, onError);
}

/**
 * Fetch meeting transcript history.
 */
export async function fetchMeeting(meetingId) {
  const data = await executeQuery(GET_MEETING, { meeting_id: meetingId });
  return data.getMeeting.items;
}

/**
 * Fetch action log for a meeting.
 */
export async function fetchActions(meetingId) {
  const data = await executeQuery(GET_ACTIONS, { meeting_id: meetingId });
  return data.getActions.items;
}
