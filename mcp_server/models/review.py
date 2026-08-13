from sqlalchemy import Column, BigInteger, String, Float, Text, Date, DateTime, func
from database.mysql_connection import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    site = Column(String(50), nullable=False, index=True)
    review_date = Column(Date, nullable=False)
    rating = Column(Float, nullable=False)
    content = Column(Text, nullable=False)
    cleaned_review = Column(Text)
    day_of_week = Column(String(10))
    tf_idf_mean_score = Column(Float)
    collected_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())