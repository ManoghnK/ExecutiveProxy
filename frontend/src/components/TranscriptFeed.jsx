import React, { useRef, useEffect } from 'react';

const TranscriptFeed = ({ transcripts = [] }) => {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [transcripts]);

    const getIntentColor = (intent) => {
        switch (intent) {
            case 'JIRA_TICKET': return 'border-blue-500';
            case 'CALENDAR_EVENT': return 'border-green-500';
            case 'POLICY_RISK': return 'border-red-500';
            default: return 'border-gray-600';
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#1a1a1a] border-r border-[#333] p-4 overflow-y-auto w-[30%]">
            <h2 className="text-xl font-bold mb-4 text-[#e5e5e5]">Transcript</h2>
            <div className="flex-1 space-y-4">
                {transcripts.length === 0 ? (
                    <div className="text-gray-500 italic text-center mt-10">Waiting for audio...</div>
                ) : (
                    transcripts.map((t, idx) => (
                        <div key={idx} className={`pl-4 border-l-4 ${getIntentColor(t.intent_label)} py-1`}>
                            <div className="flex justify-between items-center text-xs text-gray-400 mb-1">
                                <span className="font-mono">{t.speaker || 'Unknown'}</span>
                                <span>{new Date(t.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <p className="text-sm text-gray-200 whitespace-pre-wrap">{t.transcript_chunk || t.text}</p>
                        </div>
                    ))
                )}
                <div ref={bottomRef} />
            </div>
        </div>
    );
};

export default TranscriptFeed;
