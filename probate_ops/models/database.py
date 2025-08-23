from probate_ops.core.database import postgres_db
from peewee import (
    Model,
    CharField,
    TextField,
    DateField,
    IntegerField,
    BooleanField,
    FloatField,
    AutoField,
    TextField,
)


class ProbateRecord(Model):
    id = AutoField(primary_key=True)
    county = CharField()
    source_url = TextField()
    case_no = CharField()
    owner_name = CharField()  # Decedent
    property_address = CharField()  # Street Address
    city = CharField()
    state = CharField()
    zip = CharField()
    party = CharField()  # Petitioner
    mailing_address = CharField()  # Party Street+City+State+Zip
    petition_type = TextField(null=True)
    petition_date = DateField(null=True)  # ISO date
    death_date = DateField(null=True)  # ISO date
    qpublic_report_url = TextField(null=True)
    parcel_number = CharField(null=True)
    property_class = CharField(null=True)
    property_tax_district = CharField(null=True)
    property_value = FloatField(null=True)
    property_acres = FloatField(null=True)
    property_image = TextField(null=True)  # URL to image of property
    absentee_flag = BooleanField(null=True)
    days_since_petition = IntegerField(null=True)
    days_since_death = IntegerField(null=True)
    holdings_in_file = FloatField(null=True)
    score = FloatField(null=True)
    tier = CharField(null=True)  # "high" | "medium" | "
    rationale = TextField(null=True)

    class Meta:
        database = postgres_db
        # Add unique constraint on (case_no, state)
        indexes = ((("case_no", "state"), True),)
        
    @classmethod
    def from_dict(cls, data: dict):
        return {
            "county" : data.get("County"),  # Assuming all records are from the USA
            "source_url" : data.get("Source URL"),
            "case_no" : data.get("Case No"),
            "owner_name" : data.get("Decedent"),
            "property_address" : data.get("Street Address"),
            "city" : data.get("City"),
            "state" : data.get("State"),
            "zip" : data.get("Zip Code"),
            "party" : data.get("Party"),
            "mailing_address" : f"{data.get('Party Street Address')}, {data.get('Party City')}, {data.get('Party State')} {data.get('Party Zip Code')}",
            "petition_type" : data.get("Petition Type"),
            "petition_date" : data.get("Petition Date"),
            "death_date" : data.get("Death Date"),
            "qpublic_report_url" : data.get("qpublic_report_url"),
            "parcel_number" : data.get("parcel_number"),
            "property_class" : data.get("property_class"),
            "property_tax_district" : data.get("property_tax_district"),
            "property_value" : float(data.get("property_value_2025")) if data.get("property_value_2025") else None,
            "property_acres" : float(data.get("property_acres")) if data.get("property_acres") else None,
            "property_image" : data.get("property_image"),
            "absentee_flag" : None,  # Needs custom logic to determine
            "days_since_petition" : None,  # Needs custom logic to calculate
            "days_since_death" : None,  # Needs custom logic to calculate
            "holdings_in_file" : None,  # Needs custom logic to determine
            "score" : None,  # Needs custom logic to calculate
            "tier" : None,  # Needs custom logic to assign
            "rationale" : None,  # Needs custom logic to generate
        }
    
if __name__ == "__main__":
    postgres_db.connect()
    postgres_db.create_tables([ProbateRecord])
    print("Tables created successfully.")
    postgres_db.close()
