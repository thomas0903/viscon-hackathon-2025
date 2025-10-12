import type React from "react";
import './UserCard.css'

export interface UserCardProps {
  id: string;
  name: string;
  photo: string;
  description?: string;
  onClick?: (id: string) => void;
  onRemove?: (id: string) => void;
}

const UserCard: React.FC<UserCardProps> = ({ id, name, photo, description, onClick, onRemove }) => {
  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    onRemove?.(id);
  };

  return (
    <article className="friend-card" onClick={() => onClick?.(id)}>
      <img
        src={photo}
        alt={`${name}'s avatar`}
        className="friend-photo friend-photo--sm"
        loading="lazy"
        referrerPolicy="no-referrer"
      />

      <div className="friend-content">
        <div className="friend-inline">
          <span className="friend-name">{name}</span>
          {description && <span className="friend-sep">•</span>}
          {description && (
            <span className="friend-description" title={description}>
              {description}
            </span>
          )}
        </div>
      </div>

      {onRemove && (
        <button
          type="button"
          className="friend-remove"
          onClick={handleRemove}
          aria-label={`Remove ${name}`}
          title="Remove"
        >
          -
        </button>
      )}
    </article>
  );
};

export default UserCard;
