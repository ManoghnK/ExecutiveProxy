import React, { useState, useEffect, useRef } from 'react';
import TranscriptFeed from './components/TranscriptFeed.jsx';
import ActionCard from './components/ActionCard.jsx';
import RiskMatrix from './components/RiskMatrix.jsx';
import { configureAppSync, subscribeToMeeting } from './appsync-client.js';

const MEETING_ID = "demo-meeting-001";

const App = () => {
    const [isRecording, setIsRecording] = useState(false);
    const [transcripts, setTranscripts] = useState([]);
    const [actions, setActions] = useState([]);
    const [riskMatrix, setRiskMatrix] = useState(null);
    const mediaRecorderRef = useRef(null);
    const [config, setConfig] = useState(null);

    useEffect(() => {
        // Load config and init AppSync
        window.electronAPI.getConfig().then(cfg => {
            setConfig(cfg);
            if (cfg.appSyncUrl && cfg.appSyncKey) {
                configureAppSync(cfg);
                
                // Subscribe
                const unsubscribe = subscribeToMeeting(
                    MEETING_ID,
                    (transcript) => {
                        setTranscripts(prev => [...prev, transcript]);
                    },
                    (action) => {
                        setActions(prev => {
                            // Deduplicate or update existing actions
                            const index = prev.findIndex(a => a.action_id === action.action_id);
                            if (index >= 0) {
                                const newActions = [...prev];
                                newActions[index] = action;
                                return newActions;
                            }
                            return [...prev, action];
                        });
                        
                        // Update Risk Matrix if action is POLICY_RISK
                        if (action.action_type === 'POLICY_RISK' && action.result) {
                             // Assuming result contains risk details. 
                             // Adjust based on actual payload structure.
                             try {
                                const resultObj = typeof action.result === 'string' ? JSON.parse(action.result) : action.result;
                                setRiskMatrix(resultObj);
                             } catch(e) {
                                console.error("Failed to parse risk result", e);
                             }
                        }
                    }
                );
                return () => unsubscribe && unsubscribe();
            }
        });

        // Listen for transcript chunks from Main (processed by Lambda directly via HTTP response)
        window.electronAPI.onTranscriptChunk((chunk) => {
            console.log("Direct chunk:", chunk);
            if (chunk.transcript) {
                setTranscripts(prev => [...prev, {
                    timestamp: chunk.timestamp || new Date().toISOString(),
                    speaker: chunk.speaker || "You",
                    transcript_chunk: chunk.transcript,
                    intent_label: chunk.intent_label || "NO_ACTION"
                }]);
            }
        });
        
    }, []);

    const sendManualInput = async (e) => {
        e.preventDefault();
        const input = e.target.elements['manual-input'].value;
        if (!input) return;

        try {
            await window.electronAPI.sendManualInput({
                meetingId: MEETING_ID,
                text: input,
                timestamp: new Date().toISOString()
            });
            e.target.reset();
        } catch (err) {
            console.error("Manual input failed", err);
            alert("Failed to send manual input: " + err.message);
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // specific mimeType for Nova 2 Sonic? 
            // "Use MediaRecorder with mimeType 'audio/webm;codecs=opus'"
            const options = { mimeType: 'audio/webm;codecs=opus' };
            const mediaRecorder = new MediaRecorder(stream, options);
            mediaRecorderRef.current = mediaRecorder;

            mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0) {
                    const blob = event.data;
                    const buffer = await blob.arrayBuffer();
                    const base64 = btoa(new Uint8Array(buffer).reduce((data, byte) => data + String.fromCharCode(byte), ''));
                    
                    window.electronAPI.sendAudioChunk({
                        meetingId: MEETING_ID,
                        audioBase64: base64,
                        timestamp: new Date().toISOString()
                    });
                }
            };

            // Slice every 5 seconds
            mediaRecorder.start(5000);
            setIsRecording(true);
            window.electronAPI.startRecording(); // Signal main process
        } catch (err) {
            console.error("Error starting recording:", err);
            alert("Could not access microphone.");
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
        }
        setIsRecording(false);
        window.electronAPI.stopRecording();
    };

    return (
        <div className="flex flex-col h-screen text-[#e5e5e5] font-sans">
            {/* Top Bar */}
            <div className="h-16 bg-[#1a1a1a] border-b border-[#333] flex items-center justify-between px-6">
                <div className="flex items-center gap-4">
                    <h1 className="text-xl font-bold tracking-wider text-white">EXECUTIVE PROXY</h1>
                    <span className="flex items-center gap-2 text-xs font-bold text-red-500 animate-pulse bg-red-900/20 px-2 py-1 rounded">
                        <span>●</span> LIVE
                    </span>
                </div>
                
                <button 
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`px-6 py-2 rounded font-bold transition-all ${
                        isRecording 
                        ? 'bg-red-600 hover:bg-red-700 text-white shadow-[0_0_15px_rgba(220,38,38,0.5)]' 
                        : 'bg-[#00d4ff] hover:bg-[#00a3cc] text-black shadow-[0_0_15px_rgba(0,212,255,0.5)]'
                    }`}
                >
                    {isRecording ? 'STOP RECORDING' : 'START RECORDING'}
                </button>
            </div>

            {/* Main Content */}
            <div className="flex flex-1 overflow-hidden">
                {/* LEFT: Transcript */}
                <TranscriptFeed transcripts={transcripts} />

                {/* CENTER: Actions */}
                <div className="flex-1 bg-[#0f0f0f] p-6 flex flex-col w-[40%] overflow-hidden">
                    <h2 className="text-xl font-bold mb-4 text-[#e5e5e5]">Detected Actions</h2>
                    <div className="flex-1 overflow-y-auto pr-2">
                        {actions.length === 0 ? (
                            <div className="text-center mt-20 text-gray-600">
                                <p className="text-lg mb-2">No actions detected yet</p>
                                <p className="text-sm">Speak clearly to trigger Jira, Calendar, or Policy checks.</p>
                            </div>
                        ) : (
                            actions.map((action, idx) => (
                                <ActionCard key={action.action_id || idx} action={action} />
                            ))
                        )}
                    </div>
                    
                    {/* Manual Input Fallback */}
                    <div className="mt-4 pt-4 border-t border-[#333]">
                        <form className="flex gap-2" onSubmit={sendManualInput}>
                            <input 
                                name="manual-input"
                                type="text" 
                                placeholder="Type a command manually..." 
                                className="flex-1 bg-[#1a1a1a] border border-[#333] rounded px-4 py-2 text-sm focus:outline-none focus:border-[#00d4ff]"
                            />
                            <button className="bg-[#333] hover:bg-[#444] px-4 py-2 rounded text-sm font-bold">
                                SEND
                            </button>
                        </form>
                    </div>
                </div>

                {/* RIGHT: Risk Matrix */}
                <RiskMatrix riskData={riskMatrix} />
            </div>
        </div>
    );
};

export default App;
