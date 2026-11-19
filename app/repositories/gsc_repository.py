from app.database.connection import get_database
from app.models.gsc import GSCDocument

def save_gsc_data(data: GSCDocument):
    db = get_database()
    document = data.model_dump()
    db.gsc_data.update_one(
        {
        "client_id": document['client_id'],
        "property_url": document['property_url'],
        "period.type": document['period']['type'],
        "period.start_date": document['period']['start_date'],
        "period.end_date": document['period']['end_date'],
        "dimension_type": document['dimension_type'],
        "dimension_key": document['dimension_key']
        },
        {
            "$set" : document
        },
        upsert=True
    )

print("GSC data saved successfully")