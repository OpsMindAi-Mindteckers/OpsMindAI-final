/**
 * Example: Testing agent component
 */

'use client';

import { useState } from 'react';
import { useTesting } from '@/lib/hooks';

export default function TestingAgentExample() {
  const { generateTests, pollJobStatus, isLoading, error } = useTesting();
  const [repoUrl, setRepoUrl] = useState('');
  const [jobId, setJobId] = useState('');
  const [jobStatus, setJobStatus] = useState<any>(null);

  const handleGenerateTests = async (e: React.FormEvent) => {
    e.preventDefault();

    const result = await generateTests({
      repo_url: repoUrl,
      branch: 'main',
      framework: 'pytest',
      coverage_threshold: 0.80,
    });

    if (result?.job_id) {
      setJobId(result.job_id);
      // Start polling
      pollForCompletion(result.job_id);
    }
  };

  const pollForCompletion = async (id: string) => {
    const finalStatus = await pollJobStatus(id);
    if (finalStatus) {
      setJobStatus(finalStatus);
    }
  };

  return (
    <div>
      <h1>Testing Agent</h1>

      <form onSubmit={handleGenerateTests}>
        <div>
          <label htmlFor="repo">Repository URL:</label>
          <input
            id="repo"
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            required
          />
        </div>

        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Generating...' : 'Generate Tests'}
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>Error: {error}</p>}

      {jobId && (
        <div style={{ marginTop: '20px' }}>
          <p>Job ID: {jobId}</p>
          {jobStatus && (
            <div style={{ border: '1px solid #ccc', padding: '20px' }}>
              <p>Status: {jobStatus.status}</p>
              {jobStatus.coverage && (
                <div>
                  <h3>Coverage</h3>
                  <p>Coverage: {(jobStatus.coverage.coverage_pct * 100).toFixed(2)}%</p>
                  <p>Gate Passed: {jobStatus.coverage.gate_passed ? 'Yes' : 'No'}</p>
                </div>
              )}
              {jobStatus.generated_files && (
                <div>
                  <h3>Generated Files</h3>
                  {jobStatus.generated_files.map((file, i) => (
                    <div key={i}>
                      <p>
                        {file.source_file} → {file.output_file}
                      </p>
                      <p>Functions: {file.functions_processed}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
