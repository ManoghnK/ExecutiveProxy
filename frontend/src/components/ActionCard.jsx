import React from 'react';

const ActionCard = ({ action }) => {
    const { action_type, status, payload, result, created_at } = action;

    const getStatusIcon = (s) => {
        switch (s) {
            case 'PENDING': return '⏳';
            case 'COMPLETED': return '✅';
            case 'FAILED': return '❌';
            case 'HANDOFF': return '➡️';
            default: return '❓';
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

    return (
        <div className="bg-[#1a1a1a] border-l-4 border-gray-700 rounded-lg p-3 mb-3 shadow-lg hover:bg-[#252525] transition-colors relative">
            <div className={`absolute top-0 right-0 p-1 text-xs font-bold ${getStatusIcon(status) === '✅' ? 'text-green-400' : 'text-yellow-400'}`}>
                {getStatusIcon(status)}
            </div>
            <div className="flex items-center gap-2 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold text-white uppercase tracking-wider ${getIntentColor(action_type)}`}>
                    {action_type}
                </span>
                <span className="text-xs text-gray-500">{new Date(created_at).toLocaleTimeString()}</span>
            </div>
            
            <p className="text-sm font-medium text-gray-200 mb-1">{action.summary || 'Executing action...'}</p>
            
            {result && (
                <div className="mt-2 text-xs font-mono bg-[#0f0f0f] p-2 rounded text-blue-300 overflow-x-auto">
                    {JSON.stringify(result, null, 2)}
                </div>
            )}
        </div>
    );
};

export default ActionCard;
