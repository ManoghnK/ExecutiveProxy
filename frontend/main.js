const { app, BrowserWindow, ipcMain, desktopCapturer } = require('electron');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: path.join(__dirname, '../.env') });
const { LambdaClient, InvokeCommand } = require('@aws-sdk/client-lambda');
const { execSync } = require('child_process');

let mainWindow;
let recordingInterval;

// Manually fetch credentials using AWS CLI because SDK v3 does not natively support `login_session` in ~/.aws/config
let awsCredentials = undefined;
try {
  const envExport = execSync('aws configure export-credentials --format env', { encoding: 'utf-8' });
  const creds = {};
  for (const line of envExport.split('\n')) {
    if (line.startsWith('export AWS_ACCESS_KEY_ID=')) creds.accessKeyId = line.split('=')[1].trim();
    if (line.startsWith('export AWS_SECRET_ACCESS_KEY=')) creds.secretAccessKey = line.split('=')[1].trim();
    if (line.startsWith('export AWS_SESSION_TOKEN=')) creds.sessionToken = line.split('=')[1].trim();
  }
  if (creds.accessKeyId && creds.secretAccessKey) awsCredentials = creds;
} catch (e) {
  console.log('Could not fetch AWS CLI credentials:', e.message);
}

// Configure AWS SDK
const lambda = new LambdaClient({
  region: process.env.AWS_REGION || 'us-east-1',
  credentials: awsCredentials
});

// Lambda Function Names — read from .env (with fallback to hardcoded names)
const LAMBDA_FUNCTIONS = {
    TRANSCRIBE: process.env.TRANSCRIBE_FUNCTION_NAME || 'ExecProxyLambdas-TranscribeHandler8E4C16AC-w6KnMKpV7hEC',
    CLASSIFIER: process.env.CLASSIFIER_FUNCTION_NAME || 'ExecProxyLambdas-ClassifierHandler36143077-8LCr02quojra',
    EXECUTOR:   process.env.EXECUTOR_FUNCTION_NAME   || 'ExecProxyLambdas-ExecutorHandler9E4320CC-abH97KjjunvD',
    RAG:        process.env.RAG_FUNCTION_NAME        || 'ExecProxyLambdas-RagHandler014AF978-NmHYOsU0UIeT'
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

        const command = new InvokeCommand({
            FunctionName: LAMBDA_FUNCTIONS.TRANSCRIBE,
            InvocationType: 'RequestResponse',
            Payload: Buffer.from(JSON.stringify(payload))
        });
        const result = await lambda.send(command);

        if (result.StatusCode === 200) {
            const responsePayload = JSON.parse(Buffer.from(result.Payload).toString('utf-8'));
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

        const command = new InvokeCommand({
            FunctionName: LAMBDA_FUNCTIONS.CLASSIFIER,
            InvocationType: 'RequestResponse',
            Payload: Buffer.from(JSON.stringify(payload))
        });
        const result = await lambda.send(command);
        
        return JSON.parse(Buffer.from(result.Payload).toString('utf-8'));
    } catch (err) {
        console.error("Error invoking Classifier lambda:", err);
        throw err;
    }
});

ipcMain.handle('classify-text', async (event, data) => {
  try {
    // Step 1: Classify (reuse the top-level lambda client)
    const command = new InvokeCommand({
      FunctionName: LAMBDA_FUNCTIONS.CLASSIFIER,
      InvocationType: 'RequestResponse',
      Payload: Buffer.from(JSON.stringify(data))
    });
    const classifyResult = await lambda.send(command);

    const payload = JSON.parse(Buffer.from(classifyResult.Payload).toString('utf-8'));
    const body = typeof payload.body === 'string'
                 ? JSON.parse(payload.body) : payload.body || payload;
    const intent = body.intent || 'NO_ACTION';
    const confidence = body.confidence || 0;

    console.log('=== INTENT:', intent);
    console.log('=== CONFIDENCE:', confidence);
    console.log('=== BODY:', JSON.stringify(body));

    // Send transcript update to frontend
    event.sender.send('transcript-chunk', {
      text: data.transcript_chunk,
      speaker: data.speaker || 'Manual',
      timestamp: data.timestamp,
      intent_label: intent
    });

    // Step 2: If actionable, execute locally via Python subprocess
    if (intent !== 'NO_ACTION' && confidence >= 0.75) {
      const actionId = Date.now().toString();
      const executorPayload = {
        action_id: actionId,
        meeting_id: data.meeting_id,
        intent: intent,
        extracted_action: body.extracted_action || data.transcript_chunk,
        entities: body.entities || {}
      };

      // Send PENDING action card to frontend immediately
      event.sender.send('action-update', {
        meeting_id: data.meeting_id,
        action_id: actionId,
        action_type: intent,
        status: 'PENDING',
        status_message: 'Queued for execution...',
        result: null,
        created_at: new Date().toISOString()
      });

      // Spawn local executor subprocess
      const { spawn } = require('child_process');
      const pythonPath = path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe');
      const scriptPath = path.join(__dirname, 'local_executor.py');

      // Fallback to system python if venv doesn't exist
      const fs = require('fs');
      const pythonCmd = fs.existsSync(pythonPath) ? pythonPath : 'python';

      console.log(`Spawning local executor: ${pythonCmd} ${scriptPath}`);

      const child = spawn(pythonCmd, [scriptPath], {
        cwd: __dirname,
        env: { ...process.env, NOVA_ACT_ENABLED: 'true' }
      });

      // Send payload to stdin
      child.stdin.write(JSON.stringify(executorPayload));
      child.stdin.end();

      // Listen for JSON status lines on stdout
      let stdoutBuffer = '';
      child.stdout.on('data', (chunk) => {
        stdoutBuffer += chunk.toString();
        // Process complete lines
        const lines = stdoutBuffer.split('\n');
        stdoutBuffer = lines.pop(); // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const update = JSON.parse(line);
            console.log(`Executor status: ${update.status} - ${update.message}`);

            // Send status update to frontend
            event.sender.send('action-update', {
              meeting_id: data.meeting_id,
              action_id: actionId,
              action_type: intent,
              status: update.status,
              status_message: update.message || '',
              result: update.data ? JSON.stringify(update.data) : null,
              created_at: new Date().toISOString()
            });
          } catch (e) {
            console.log('Executor output:', line);
          }
        }
      });

      child.stderr.on('data', (chunk) => {
        console.error('Executor stderr:', chunk.toString());
      });

      child.on('close', (code) => {
        console.log(`Executor process exited with code ${code}`);
        if (code !== 0) {
          // Send FAILED status if process crashed
          event.sender.send('action-update', {
            meeting_id: data.meeting_id,
            action_id: actionId,
            action_type: intent,
            status: 'FAILED',
            status_message: `Executor process exited with code ${code}`,
            result: null,
            created_at: new Date().toISOString()
          });
        }
      });
    }

    return { intent, confidence };
  } catch(e) {
    console.error('classify-text error:', e);
    return { error: e.message };
  }
});
