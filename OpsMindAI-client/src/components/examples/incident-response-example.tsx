/**
 * Example: SRE incident component
 */

'use client';

import { useEffect, useState } from 'react';
import { useSRE } from '@/lib/hooks';
import { AlertSource, IncidentSeverity } from '@/lib/api-types';

export default function IncidentResponseExample() {
  const { incident, isLoading, error, ingestAlert, triggerRCA, getIncident } = useSRE();
  const [selectedIncident, setSelectedIncident] = useState<string>('');

  const handleReportAlert = async () => {
    const result = await ingestAlert({
      source: AlertSource.PROMETHEUS,
      service: 'payment-api',
      severity: IncidentSeverity.HIGH,
      alert_name: 'HighErrorRate',
      labels: {
        instance: 'payment-1',
      },
      annotations: {
        description: 'Error rate is above 5%',
      },
    });

    if (result?.incident_id) {
      setSelectedIncident(result.incident_id);
      // Poll for incident details
      setTimeout(() => {
        getIncident(result.incident_id);
      }, 1000);
    }
  };

  const handleTriggerRCA = async () => {
    if (selectedIncident) {
      await triggerRCA({ incident_id: selectedIncident });
    }
  };

  return (
    <div>
      <h1>SRE Incident Response</h1>

      <button onClick={handleReportAlert} disabled={isLoading}>
        Report Alert
      </button>

      {error && <p style={{ color: 'red' }}>Error: {error}</p>}

      {isLoading && <p>Loading...</p>}

      {incident && (
        <div style={{ marginTop: '20px', border: '1px solid #ccc', padding: '20px' }}>
          <h2>{incident.alert_name}</h2>
          <p>Service: {incident.service}</p>
          <p>Severity: {incident.severity}</p>
          <p>Status: {incident.status}</p>

          {incident.rca_result && (
            <div>
              <h3>Root Cause Analysis</h3>
              <p>Root Cause: {incident.rca_result.root_cause}</p>
              <p>Confidence: {(incident.rca_result.confidence * 100).toFixed(2)}%</p>
              {incident.rca_result.remediation_steps && (
                <div>
                  <h4>Remediation Steps:</h4>
                  <ul>
                    {incident.rca_result.remediation_steps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <button onClick={handleTriggerRCA} disabled={isLoading || !selectedIncident}>
            Trigger RCA
          </button>

          {incident.timeline && (
            <div>
              <h3>Timeline</h3>
              {incident.timeline.map((event, i) => (
                <div key={i} style={{ marginBottom: '10px' }}>
                  <strong>{event.event_type}</strong> - {event.timestamp}
                  <p>{event.description}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
