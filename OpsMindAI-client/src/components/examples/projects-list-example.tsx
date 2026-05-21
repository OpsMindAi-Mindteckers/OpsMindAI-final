/**
 * Example: Projects list component
 */

'use client';

import { useEffect } from 'react';
import { useProjects } from '@/lib/hooks';
import Link from 'next/link';

export default function ProjectsListExample() {
  const { projects, isLoading, error, listProjects } = useProjects();

  useEffect(() => {
    listProjects();
  }, [listProjects]);

  if (isLoading) return <div>Loading projects...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;

  return (
    <div>
      <h1>My Projects</h1>
      {projects.length === 0 ? (
        <p>No projects yet. Create one to get started!</p>
      ) : (
        <div className="grid gap-4">
          {projects.map((project) => (
            <div
              key={project.project_id}
              style={{
                border: '1px solid #ccc',
                padding: '20px',
                borderRadius: '8px',
              }}
            >
              <h3>{project.name}</h3>
              <p>Status: {project.status}</p>
              <p>{project.prompt}</p>
              <Link href={`/projects/${project.project_id}`}>View Details</Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
