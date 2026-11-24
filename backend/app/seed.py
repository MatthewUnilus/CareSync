from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, build_engine, build_session_factory
from app.models import Role, User
from app.security import hash_password


@dataclass(frozen=True)
class DemoUser:
    email: str
    display_name: str
    role: Role
    password: str


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser(
        email="clinical@example.com",
        display_name="Clinical Demo User",
        role=Role.clinical,
        password="clinical-password",
    ),
    DemoUser(
        email="laboratory@example.com",
        display_name="Laboratory Demo User",
        role=Role.laboratory,
        password="laboratory-password",
    ),
    DemoUser(
        email="administrator@example.com",
        display_name="Administrator Demo User",
        role=Role.administrator,
        password="administrator-password",
    ),
)


def seed_demo_users(session: Session) -> list[DemoUser]:
    """Create the demo accounts if they do not exist."""
    created: list[DemoUser] = []
    for spec in DEMO_USERS:
        exists = session.scalar(select(User).where(User.email == spec.email))
        if exists is not None:
            continue
        session.add(
            User(
                email=spec.email,
                display_name=spec.display_name,
                role=spec.role.value,
                password_hash=hash_password(spec.password),
            )
        )
        created.append(spec)
    return created


def main() -> None:
    from app.config import get_settings

    settings = get_settings()
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        created = seed_demo_users(session)
        session.commit()

    if created:
        print("Seeded demo users:")
        for spec in created:
            print(f"  {spec.role.value:<14} {spec.email} / {spec.password}")
    else:
        print("Demo users already present; nothing to seed.")
    print(f"Database: {settings.database_url}")


if __name__ == "__main__":
    main()
