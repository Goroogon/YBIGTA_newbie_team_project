from typing import Optional
from sqlalchemy import Column, String
from sqlalchemy.orm import Session

from app.user.user_schema import User
from database.mysql_connection import Base


class UserORM(Base):
    __tablename__ = "users"

    email = Column(String(255), primary_key=True, index=True)
    password = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> Optional[User]:
        user_orm = self.db.query(UserORM).filter(UserORM.email == email).first()
        if user_orm is None:
            return None
        return User(
            email=user_orm.email,
            password=user_orm.password,
            username=user_orm.username,
        )

    def save_user(self, user: User) -> User:
        user_orm = self.db.query(UserORM).filter(UserORM.email == user.email).first()

        if user_orm:
            user_orm.password = user.password
            user_orm.username = user.username
        else:
            user_orm = UserORM(
                email=user.email,
                password=user.password,
                username=user.username,
            )
            self.db.add(user_orm)

        self.db.commit()
        self.db.refresh(user_orm)

        return User(
            email=user_orm.email,
            password=user_orm.password,
            username=user_orm.username,
        )

    def delete_user(self, user: User) -> User:
        user_orm = self.db.query(UserORM).filter(UserORM.email == user.email).first()
        if user_orm is None:
            return user

        self.db.delete(user_orm)
        self.db.commit()

        return user