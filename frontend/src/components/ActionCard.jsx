import React from 'react';

const ActionCard = ({ action }) => {
    const { action_type, status, result, created_at, status_message } = action;

    const getStatusIcon = (s) => {
        switch (s) {
            case 'PENDING': return '⏳';
            case 'IN_PROGRESS': return '🔄';
            case 'COMPLETED': return '✅';
            case 'FAILED': return '❌';
            case 'HANDOFF': return '➡️';
            default: return '❓';
        }
    };

    const getStatusColor = (s) => {
        switch (s) {
            case 'PENDING': return 'text-yellow-400';
            case 'IN_PROGRESS': return 'text-cyan-400';
            case 'COMPLETED': return 'text-green-400';
            case 'FAILED': return 'text-red-400';
            default: return 'text-gray-400';
        }
    };

    const getIntentColor = (intent) => {
        switch (intent) {
            case 'JIRA_TICKET': return 'bg-blue-600';
            case 'CALENDAR_EVENT': return 'bg-green-600';
            case 'POLICY_RISK': return 'bg-red-600';
            default: return 'bg-gray-600';
        }
    };

    const getIntentLabel = (intent) => {
        switch (intent) {
            case 'JIRA_TICKET': return 'JIRA';
            case 'CALENDAR_EVENT': return 'CALENDAR';
            case 'POLICY_RISK': return 'POLICY';
            default: return intent;
        }
    };

    const getBorderColor = (s) => {
        switch (s) {
            case 'PENDING': return 'border-yellow-500/50';
            case 'IN_PROGRESS': return 'border-cyan-500/50';
            case 'COMPLETED': return 'border-green-500/50';
            case 'FAILED': return 'border-red-500/50';
            default: return 'border-gray-700';
        }
    };

    // Parse result for display
    let resultDisplay = null;
    if (status === 'COMPLETED' && result) {
        try {
            const resultObj = typeof result === 'string' ? JSON.parse(result) : result;
            const ticketId = resultObj.ticket_id || resultObj.key;
            const ticketUrl = resultObj.ticket_url || resultObj.self;
            if (ticketId) {
                resultDisplay = (
                    <div className="mt-2 flex items-center gap-2 text-sm">
                        <span className="text-green-400 font-bold">{ticketId}</span>
                        {ticketUrl && (
                            <span className="text-gray-500 text-xs truncate">{ticketUrl}</span>
                        )}
                    </div>
                );
            }
        } catch (e) {
            // Fallback: show raw result
        }
    }

    if (status === 'FAILED' && result) {
        try {
            const resultObj = typeof result === 'string' ? JSON.parse(result) : result;
            resultDisplay = (
                <div className="mt-2 text-xs font-mono bg-red-900/20 border border-red-800/30 p-2 rounded text-red-300">
                    {resultObj.error || JSON.stringify(resultObj)}
                </div>
            );
        } catch (e) {
            resultDisplay = (
                <div className="mt-2 text-xs font-mono bg-red-900/20 border border-red-800/30 p-2 rounded text-red-300">
                    {result}
                </div>
            );
        }
    }

    return (
        <div className={`bg-[#1a1a1a] border-l-4 ${getBorderColor(status)} rounded-lg p-3 mb-3 shadow-lg hover:bg-[#252525] transition-all relative`}>
            {/* Status icon */}
            <div className={`absolute top-2 right-2 text-sm ${getStatusColor(status)} ${status === 'IN_PROGRESS' ? 'animate-spin' : ''}`}>
                {getStatusIcon(status)}
            </div>

            {/* Intent badge + timestamp */}
            <div className="flex items-center gap-2 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold text-white uppercase tracking-wider ${getIntentColor(action_type)}`}>
                    {getIntentLabel(action_type)}
                </span>
                <span className="text-xs text-gray-500">
                    {action_type}
                </span>
            </div>

            {/* Timestamp */}
            <div className="text-xs text-gray-600 mb-1">
                {new Date(created_at).toLocaleTimeString()}
            </div>

            {/* Status message */}
            {status_message && (
                <div className={`text-sm ${getStatusColor(status)} ${status === 'IN_PROGRESS' ? 'animate-pulse' : ''}`}>
                    {status_message}
                </div>
            )}

            {/* Result display */}
            {resultDisplay}
        </div>
    );
};

export default ActionCard;
