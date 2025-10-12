import UserBubble from './UserBubble';
import "./EventNode.css"

export function EventNode(props: any) {

  return (
    <div>
      <div style={{
        padding: '15px',
        borderRadius: '8px',
        border: '2px solid #6366f1',
        background: 'white',
        width: `${200 + 50 * props.data.total_attendees}px`,
        height: `${200 + 50 * props.data.total_attendees}px`,
      }}>
        <h1>{props.data.name}</h1>
        <p>{props.data.description}</p>

      </div>
      <div style={{ display: 'flex', position: 'relative', top: '-25px', flexWrap: 'wrap', width: '250px'}}>
        {props.data.friends.map((friend: any, index: number) => (
          <div
            key={index}
          >
            <UserBubble src={friend.profilePictureUrl} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default EventNode;