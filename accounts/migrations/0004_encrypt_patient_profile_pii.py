
import clinic.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_customuser_managers_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patientprofile',
            name='address',
            field=clinic.encrypted_fields.EncryptedTextField(blank=True, help_text='Encrypted address'),
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='date_of_birth',
            field=clinic.encrypted_fields.EncryptedDateField(blank=True, help_text='Encrypted date of birth', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='phone',
            field=clinic.encrypted_fields.EncryptedCharField(blank=True, help_text='Encrypted phone number', max_length=255),
        ),
    ]
