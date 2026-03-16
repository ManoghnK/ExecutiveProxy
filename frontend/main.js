const { app, BrowserWindow, ipcMain, desktopCapturer } = require('electron');
const path = require('path');
const fs = require('fs');
const AWS = require('aws-sdk');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

let mainWindow;
let recordingInterval;

// Configure AWS SDK
// AWS credentials come from environment/profile automatically
AWS.config.update({ region: process.env.AWS_REGION || 'us-east-1' });
const lambda = new AWS.Lambda();

// Lambda Function Names (Updated to use direct invocation instead of URLs)
const LAMBDA_FUNCTIONS = {
    TRANSCRIBE: 'ExecProxyLambdas-TranscribeHandler8E4C16AC-w6KnMKpV7hEC',
    CLASSIFIER: 'ExecProxyLambdas-ClassifierHandler36143077-8LCr02quojra',
    EXECUTOR:   'ExecProxyLambdas-ExecutorHandler9E4320CC-abH97KjjunvD',
    RAG:        'ExecProxyLambdas-RagHandler014AF978-NmHYOsU0UIeT'
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 800,
    backgroundColor: '#0f0f0f',
    alwaysOnTop: true,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false, // Allow loading local resources via Babel
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.loadFile('src/index.html');
  mainWindow.webContents.openDevTools();
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// IPC Handlers
ipcMain.handle('get-config', () => ({
    appSyncUrl: process.env.APPSYNC_API_URL,
    appSyncKey: process.env.APPSYNC_API_KEY
}));

ipcMain.handle('start-recording', async (event) => {
  console.log('Start recording initialized');
  return { status: 'started' };
});

ipcMain.handle('stop-recording', async (event) => {
  console.log('Stop recording requested');
  return { status: 'stopped' };
});

ipcMain.handle('send-audio-chunk', async (event, { audioBase64, timestamp, meetingId }) => {
    try {
        const payload = {
            meeting_id: meetingId || "demo-meeting-001",
            audio_base64: audioBase64,
            timestamp: timestamp
        };

        const result = await lambda.invoke({
            FunctionName: LAMBDA_FUNCTIONS.TRANSCRIBE,
            InvocationType: 'RequestResponse',
            Payload: JSON.stringify(payload)
        }).promise();

        if (result.StatusCode === 200) {
            const responsePayload = JSON.parse(result.Payload);
            // Emit content back to renderer if valid
            if (responsePayload && (responsePayload.transcript || responsePayload.intent_label)) {
                mainWindow.webContents.send('transcript-chunk', responsePayload);
            }
        } else {
            console.error(`Lambda invoke error: ${result.FunctionError}`, result);
        }
    } catch (err) {
        console.error("Error invoking Transcribe lambda:", err);
    }
});

ipcMain.handle('send-manual-input', async (event, { text, timestamp, meetingId }) => {
    try {
        const payload = {
            meeting_id: meetingId || "demo-meeting-001",
            transcript_chunk: text,
            speaker: "Manual",
            timestamp: timestamp
        };

        const result = await lambda.invoke({
            FunctionName: LAMBDA_FUNCTIONS.CLASSIFIER,
            InvocationType: 'RequestResponse',
            Payload: JSON.stringify(payload)
        }).promise();
        
        return JSON.parse(result.Payload);
    } catch (err) {
        console.error("Error invoking Classifier lambda:", err);
        throw err;
    }
});

ipcMain.handle('classify-text', async (event, data) => {
  const AWS = require('aws-sdk');
  const lambda = new AWS.Lambda({ region: 'us-east-1' });
  
  try {
    console.log('=== CLASSIFY-TEXT INPUT:', JSON.stringify(data));
    
    const result = await lambda.invoke({
      FunctionName: 'ExecProxyLambdas-ClassifierHandler36143077-8LCr02quojra',
      InvocationType: 'RequestResponse',
      Payload: JSON.stringify(data)
    }).promise();
    
    console.log('=== RAW LAMBDA RESULT:', JSON.stringify(result));
    console.log('=== PAYLOAD STRING:', result.Payload);

    // Parse Lambda response payload.
    // If Lambda returns { statusCode, body }, we need to parse body.
    let payload;
    try {
        payload = JSON.parse(result.Payload);
    } catch (e) {
        payload = result.Payload;
    }
    
    console.log('=== PARSED PAYLOAD:', JSON.stringify(payload));

    const body = typeof payload.body === 'string' 
                 ? JSON.parse(payload.body) : payload.body || payload;
    console.log('=== BODY:', JSON.stringify(body));
    
    // Transform to ActionLog format
    const actionUpdate = {
      meeting_id: data.meeting_id || "demo-meeting-001",
      action_id: Date.now().toString(),
      action_type: body.intent || 'NO_ACTION',
      status: 'COMPLETED', // Since we only classified, we assume intent classification is done. 
                           // But if we want to run executor, we might need more logic here?
                           // For now, this matches the user request.
      result: JSON.stringify(body),
      created_at: new Date().toISOString()
    };
    
    // Only send to frontend if actionable
    if (actionUpdate.action_type !== 'NO_ACTION') {
      event.sender.send('action-update', actionUpdate);
    }
    
    // Also send transcript update with intent label
    // Check if we already have transcript in data
    event.sender.send('transcript-chunk', {
      text: data.transcript_chunk,
      speaker: data.speaker || 'Manual',
      timestamp: data.timestamp,
      intent_label: body.intent || 'NO_ACTION'
    });
    
    return actionUpdate;
  } catch(e) {
    console.error('classify-text error:', e);
    return { error: e.message };
  }
});
