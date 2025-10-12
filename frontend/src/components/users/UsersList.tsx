import UserCard from "./UserCard";
import './UsersList.css'

export interface User {
  id: string;
  name: string;
  photo: string;
}

export const UsersList = ({ users, onRemove, onClick }: { users: User[], onRemove?: (id: string) => void, onClick?: (id: string) => void }) => {
  console.log(users);

  return (
    <div className="users-list">
      {users.map((f) => (
        <UserCard
          key={f.id}
          id={f.id}
          name={f.name}
          photo={f.photo}
          onClick={onClick}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
};
