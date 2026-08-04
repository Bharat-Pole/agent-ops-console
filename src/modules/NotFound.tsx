import { Link } from 'react-router-dom';
import { EmptyState, Button } from '@/components/primitives';
import { Compass } from 'lucide-react';

export default function NotFound() {
  return (
    <EmptyState
      icon={<Compass size={28} />}
      title="Page not found"
      message="That route doesn't exist in the console."
      action={
        <Link to="/home">
          <Button variant="primary">Back to Home</Button>
        </Link>
      }
    />
  );
}
