interface UserBubbleProps {
  src?: string | null | undefined;
}

export function UserBubble({ src = '/res/Portrait_Placeholder.png' }: UserBubbleProps) {
  return (
    <div style={{
      borderRadius: '50%',
      border: '1px solid #6366f1',
      background: 'white',
      width: 60,
      height: 60,
      position: 'relative',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
    }}>
      <img 
        src={src || '/res/Portrait_Placeholder.png'}
        alt="PHOTO"
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '50%',
          objectFit: 'cover'
        }}
      />
    </div>
  );
}

export default UserBubble;
