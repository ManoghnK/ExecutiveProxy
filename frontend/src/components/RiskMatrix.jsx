import React from 'react';

const RiskMatrix = ({ riskData }) => {
    if (!riskData) {
        return (
            <div className="flex flex-col h-full bg-[#1a1a1a] border-l border-[#333] p-6 items-center justify-center text-gray-500 w-[30%]">
                <span className="text-4xl mb-4">🛡️</span>
                <p>No risks detected yet</p>
            </div>
        );
    }

    const { risk_level, violations, affected_policies, recommendation } = riskData;

    const getRiskColor = (level) => {
        switch (level?.toUpperCase()) {
            case 'LOW': return 'bg-green-600 text-white';
            case 'MEDIUM': return 'bg-yellow-500 text-black';
            case 'HIGH': return 'bg-orange-600 text-white';
            case 'CRITICAL': return 'bg-red-600 text-white animate-pulse';
            default: return 'bg-gray-600 text-white';
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#1a1a1a] border-l border-[#333] p-6 w-[30%] overflow-y-auto">
            <h2 className="text-xl font-bold mb-6 text-[#e5e5e5] border-b border-gray-700 pb-2">Risk Assessment</h2>
            
            <div className={`p-4 rounded-lg text-center mb-6 shadow-md ${getRiskColor(risk_level)}`}>
                <span className="text-sm uppercase tracking-widest font-bold block mb-1">Risk Level</span>
                <span className="text-3xl font-black block">{risk_level || 'UNKNOWN'}</span>
            </div>

            <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-400 uppercase mb-2">Policy Violations</h3>
                <ul className="list-disc pl-5 space-y-2 text-sm text-gray-300">
                    {violations?.map((v, i) => <li key={i}>{v}</li>) || <li>None detected</li>}
                </ul>
            </div>

            <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-400 uppercase mb-2">Affected Policies</h3>
                <div className="flex flex-wrap gap-2">
                    {affected_policies?.map((p, i) => (
                        <span key={i} className="px-2 py-1 bg-blue-900 text-blue-200 rounded text-xs font-mono border border-blue-800">
                            {p}
                        </span>
                    )) || <span className="text-gray-500 text-xs">None</span>}
                </div>
            </div>

            <div>
                <h3 className="text-sm font-bold text-gray-400 uppercase mb-2">Recommendation</h3>
                <p className="text-sm italic text-gray-400 border-l-2 border-yellow-600 pl-3 py-1">
                    {recommendation || 'No action required.'}
                </p>
            </div>
        </div>
    );
};

export default RiskMatrix;
