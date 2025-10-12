import { useEffect, useState } from 'react';
import RadialEgoGraph from '../components/GraphNode';
import { getUser, type BackendUser } from '../apiClient';

export default function Network() {
  const [me, setMe] = useState<BackendUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUser()
      .then(setMe)
      .catch((e) => setError((e && e.message) || 'Failed to load user'));
  }, []);

  if (error) {
    return <div style={{ padding: 16 }}>Error: {error}</div>;
  }

  if (!me) {
    return <div style={{ padding: 16 }}>Loading…</div>;
  }

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <RadialEgoGraph userId={me.id} />
    </div>
  );
}