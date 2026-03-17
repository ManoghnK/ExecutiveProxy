const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const AWS = require('aws-sdk');
require('dotenv').config({ path: path.join(__dirname, '../.env') });
process.env.AWS_SDK_LOAD_CONFIG = '1';

let mainWindow;

// Configure AWS SDK dynamically using AWS CLI
const { execSync } = require('child_process');
let awsConfig = { region: process.env.AWS_REGION || 'us-east-1' };
try {
  const profileName = process.env.AWS_PROFILE || 'slalom_IsbUsersPS-341083262352';
  console.log('Loading fresh SSO credentials for profile:', profileName);
  const credsJson = execSync('aws configure export-credentials --profile ' + profileName).toString();
  const creds = JSON.parse(credsJson);
  awsConfig.accessKeyId = creds.AccessKeyId;
  awsConfig.secretAccessKey = creds.SecretAccessKey;
  awsConfig.sessionToken = creds.SessionToken;
  process.env.AWS_ACCESS_KEY_ID = creds.AccessKeyId;
  process.env.AWS_SECRET_ACCESS_KEY = creds.SecretAccessKey;
  process.env.AWS_SESSION_TOKEN = creds.SessionToken;
} catch (err) {
  console.log('Failed to fetch SSO credentials:', err.message);
}
AWS.config.update(awsConfig);
const lambda = new AWS.Lambda();

const LAMBDA_FUNCTIONS = {
    TRANSCRIBE: 'ExecProxyLambdas-TranscribeHandler8E4C16AC-DDTcF1AHHdJ9',
    CLASSIFIER: 'ExecProxyLambdas-ClassifierHandler36143077-IIhC1AYZnb3h',
    EXECUTOR:   'ExecProxyLambdas-ExecutorHandler9E4320CC-pAbBs21WvzCD',
    RAG:        'ExecProxyLambdas-RagHandler014AF978-qXOwhsaB0E6j'
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400, height: 800,
    backgroundColor: '#0f0f0f',
    alwaysOnTop: true, autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false, contextIsolation: true,
      webSecurity: false, preload: path.join(__dirname, 'preload.js')
    }
  });
  mainWindow.loadFile('src/index.html');
  mainWindow.webContents.openDevTools();
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

ipcMain.handle('get-config', () => ({
    appSyncUrl: process.env.APPSYNC_API_URL, appSyncKey: process.env.APPSYNC_API_KEY
}));
ipcMain.handle('start-recording', async () => ({ status: 'started' }));
ipcMain.handle('stop-recording', async () => ({ status: 'stopped' }));

ipcMain.handle('send-audio-chunk', async (event, { audioBase64, timestamp, meetingId }) => {
    try {
        const payload = { meeting_id: meetingId || 'demo-meeting-001', audio_base64: audioBase64, timestamp };
        const result = await lambda.invoke({ FunctionName: LAMBDA_FUNCTIONS.TRANSCRIBE, InvocationType: 'RequestResponse', Payload: JSON.stringify(payload) }).promise();
        if (result.StatusCode === 200) {
            const resp = JSON.parse(result.Payload);
            if (resp && (resp.transcript || resp.intent_label)) mainWindow.webContents.send('transcript-chunk', resp);
        }
    } catch (err) { console.error('Transcribe error:', err); }
});

ipcMain.handle('send-manual-input', async (event, { text, timestamp, meetingId }) => {
    try {
        const payload = { meeting_id: meetingId || 'demo-meeting-001', transcript_chunk: text, speaker: 'Manual', timestamp };
        const result = await lambda.invoke({ FunctionName: LAMBDA_FUNCTIONS.CLASSIFIER, InvocationType: 'RequestResponse', Payload: JSON.stringify(payload) }).promise();
        const resPayload = JSON.parse(result.Payload);
        if (mainWindow) {
            let body = resPayload;
            if (resPayload.body) try { body = typeof resPayload.body === 'string' ? JSON.parse(resPayload.body) : resPayload.body; } catch(e){}
            mainWindow.webContents.send('transcript-chunk', { transcript: text, intent_label: body.intent || 'NO_ACTION', speaker: 'Manual', timestamp });
        }
        return resPayload;
    } catch (err) { throw err; }
});

ipcMain.handle('classify-text', async (event, data) => {
  try {
    const listResult = await lambda.invoke({ FunctionName: LAMBDA_FUNCTIONS.CLASSIFIER, InvocationType: 'RequestResponse', Payload: JSON.stringify(data) }).promise();
    const payload = JSON.parse(listResult.Payload);
    const body = typeof payload.body === 'string' ? JSON.parse(payload.body) : payload.body || payload;
    const intent = body.intent || 'NO_ACTION';
    const confidence = body.confidence || 0;

    console.log('=== INTENT:', intent);
    console.log('=== CONFIDENCE:', confidence);
    console.log('=== BODY:', JSON.stringify(body));

    
    event.sender.send('transcript-chunk', { text: data.transcript_chunk, speaker: data.speaker || 'Manual', timestamp: data.timestamp, intent_label: intent });

    if (intent !== 'NO_ACTION' && confidence >= 0.75) {
      const executorPayload = { meeting_id: data.meeting_id, intent, extracted_action: body.extracted_action || data.transcript_chunk, entities: body.entities || {} };
      const actionId = Date.now().toString();
      
      event.sender.send('action-update', { meeting_id: data.meeting_id, action_id: actionId, action_type: intent, status: 'PENDING', result: JSON.stringify(body), created_at: new Date().toISOString() });

      
      console.log('Checks passed. Nova Act path starting...');
      if (process.env.NOVA_ACT_ENABLED === 'true' && (intent === 'JIRA_TICKET' || intent === 'CALENDAR_EVENT')) {
        const { spawn } = require('child_process');
        const pPath = process.platform === 'win32' ? path.join(__dirname, '../.venv/Scripts/python.exe') : path.join(__dirname, '../.venv/bin/python');
        const child = spawn(pPath, [path.join(__dirname, 'local_executor.py')], { env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
        
        child.stdin.write(JSON.stringify(executorPayload));
        child.stdin.end();

                child.stdout.on('data', (out) => {
          console.log('[PYTHON STDOUT]', out.toString());
          for(let line of out.toString().split('\n')) {
            if(!line.trim()) continue;
            try {
              const parsed = JSON.parse(line);
              event.sender.send('action-update', { meeting_id: data.meeting_id, action_id: actionId, action_type: intent, status: parsed.status, result: JSON.stringify(parsed.data || { message: parsed.message }), created_at: new Date().toISOString() });
            } catch(e) {}
          }
        });
        child.stderr.on('data', err => console.error('[PYTHON STDERR]', err.toString()));
        child.on('close', code => console.log('[PYTHON EXIT CODE]', code));
      } else {
        lambda.invoke({ FunctionName: LAMBDA_FUNCTIONS.EXECUTOR, InvocationType: 'Event', Payload: JSON.stringify(executorPayload) }).promise().catch(e => console.error(e));
      }
    }
    return { intent, confidence };
  } catch(e) {
    return { error: e.message };
  }
});





