from app.user.user_repository import UserRepository
from app.user.user_schema import User, UserLogin, UserUpdate

class UserService:
    def __init__(self, userRepoitory: UserRepository) -> None:
        self.repo = userRepoitory

    def login(self, user_login: UserLogin) -> User:
        ## TODO
        """
        사용자 로그인

        Args:
            user_login (UserLogin): 로그인 요청 데이터 (email, password)

        Returns:
            User: 로그인에 성공한 사용자 정보

        Raises:
            ValueError: 
                - 이메일에 해당하는 사용자가 없을 경우 ("User not Found.")
                - 비밀번호가 일치하지 않을 경우 ("Invalid ID/PW")
        """
        user = self.repo.get_user_by_email(user_login.email)
        if not user:
            raise ValueError("User not Found.")
            
        if user.password != user_login.password:
            raise ValueError("Invalid ID/PW")
            
        return user
        
    def register_user(self, new_user: User) -> User:
        ## TODO
        """
        새로운 사용자를 등록(회원가입)

        Args:
            new_user (User): 등록할 사용자 데이터 (email, password, username)

        Returns:
            User: 등록이 완료된 사용자 정보

        Raises:
            ValueError: 이메일이 이미 존재할 경우 ("User already Exists.")
        """
        user = self.repo.get_user_by_email(new_user.email)
        if user :
            raise ValueError("User already Exists.")
        new_user = self.repo.save_user(new_user)

        return new_user

    def delete_user(self, email: str) -> User:
        ## TODO
        """
        사용자를 조회한 후 삭제합니다.

        Args:
            email (str): 삭제할 사용자의 이메일 주소

        Returns:
            User: 삭제된 사용자 정보

        Raises:
            ValueError: 이메일에 해당하는 사용자가 없을 경우 ("User not Found.")
        """
        deleted_user = self.repo.get_user_by_email(email)
        if not deleted_user:
            raise ValueError("User not Found.")
            
        deleted_user = self.repo.delete_user(deleted_user)
        
        return deleted_user

    def update_user_pwd(self, user_update: UserUpdate) -> User:
        ## TODO
        """
        사용자의 비밀번호를 업데이트합니다.

        Args:
            user_update (UserUpdate): 비밀번호 변경 요청 데이터 (email, new_password)

        Returns:
            User: 비밀번호가 수정된 사용자 정보

        Raises:
            ValueError: 이메일에 해당하는 사용자가 없을 경우 ("User not Found.")
        """
        updated_user = self.repo.get_user_by_email(user_update.email)
        if not updated_user:
            raise ValueError("User not Found.")
        updated_user.password = user_update.new_password
        updated_user = self.repo.save_user(updated_user)

        return updated_user
        