from probate_ops.core.database import postgres_db
from peewee import Model, CharField, TextField, DateField, IntegerField, BooleanField, FloatField



class ProbateRecord(Model):
    id = IntegerField(primary_key=True)
    country = CharField()
    source_url = TextField()
    case_no = CharField()
    owner_name = CharField()          # Decedent
    property_address = CharField()    # Street Address
    city = CharField()
    state = CharField()
    zip = CharField()
    party = CharField()               # Petitioner
    mailing_address = CharField()     # Party Street+City+State+Zip
    petition_type = CharField()
    petition_date = DateField()       # ISO date
    death_date = DateField()          # ISO date
    qpublic_report_url = TextField(null=True)
    parcel_number = CharField(null=True)
    property_class = CharField(null=True)
    property_tax_district = CharField(null=True)
    property_value = FloatField(null=True)
    property_acres = FloatField(null=True)
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
        indexes = (
            (('case_no', 'state'), True),
        )
        
if __name__ == "__main__":
    postgres_db.connect()
    postgres_db.create_tables([ProbateRecord])
    print("Tables created successfully.")
    postgres_db.close()