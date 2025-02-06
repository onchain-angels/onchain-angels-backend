import asyncio
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from decouple import config
from nillion_sv_wrappers import SecretVaultWrapper

from core.nillion_config import config as nillion_config

@csrf_exempt
async def test_nillion(request):

    NILLION_SCHEMA_ID = config("NILLION_SCHEMA_ID")

    # Initialize the SecretVault wrapper with nodes, credentials and schema ID
    vault = SecretVaultWrapper(
        nillion_config["nodes"],
        nillion_config["org_credentials"],
        NILLION_SCHEMA_ID,
    )
    await vault.init()

    try:

        # 1. List existing schemas
        print("Existing schemas:")
        existing_schemas = await vault.get_schemas()
        print(existing_schemas)

        # 2. Define a new schema (the "%share" field will be encrypted)
        test_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Web3 Experience Survey",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "_id": {"type": "string", "format": "uuid", "coerce": True},
                    "name": {
                        "type": "object",
                        "properties": {"%share": {"type": "string"}},
                        "required": ["%share"],
                    },
                    "years_in_web3": {
                        "type": "object",
                        "properties": {"%share": {"type": "string"}},
                        "required": ["%share"],
                    },
                    "responses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rating": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 5,
                                },
                                "question_number": {"type": "integer", "minimum": 1},
                            },
                            "required": ["rating", "question_number"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["_id", "name", "years_in_web3", "responses"],
            },
        }

        # 3. Create new schema
        print("Creating new schema...")
        create_result = await vault.create_schema(
            schema=test_schema, schema_name="test_schema"
        )
        print("Creation result:", create_result)
        # Get the schema ID from the result
        schema_id = create_result[0]["result"]["data"]
        print(f"Created Schema ID: {schema_id}")

        # 4 Write data to collection (fields marked with "%allot" will be processed according to the wrapper)
        test_data = [
            {
                "name": {"%allot": "Vitalik Buterin"},
                "years_in_web3": {"%allot": 8},
                "responses": [
                    {"rating": 5, "question_number": 1},
                    {"rating": 3, "question_number": 2},
                ],
            },
            {
                "name": {"%allot": "Satoshi Nakamoto"},
                "years_in_web3": {"%allot": 14},
                "responses": [
                    {"rating": 2, "question_number": 1},
                    {"rating": 5, "question_number": 2},
                ],
            },
        ]
        write_result = await vault.write_to_nodes(test_data)
        print("Data written to nodes:", write_result)

        # 5. Read data from collection (decrypting fields as needed)
        read_result = await vault.read_from_nodes({})
        print("Data read (first 5 records):", read_result[:5])

        # 6. Delete the created schema
        print("Deleting schema...")
        delete_result = await vault.delete_schema(schema_id)
        print("Deletion result:", delete_result)

        return HttpResponse("Test completed successfully", status=200)

    except Exception as e:
        print(f"Error during operation: {str(e)}")
        return HttpResponse(f"Error during operation: {str(e)}", status=400)
