
import clinic.encrypted_fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('clinic', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='diagnosis',
            field=clinic.encrypted_fields.EncryptedTextField(blank=True, help_text="Doctor's diagnosis after completion."),
        ),
        migrations.AlterField(
            model_name='medicalnote',
            name='content',
            field=clinic.encrypted_fields.EncryptedTextField(),
        ),
    ]
