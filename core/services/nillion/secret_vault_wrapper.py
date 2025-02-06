import asyncio
import uuid
import time
from typing import List, Dict, Any

import httpx
import jwt
from jwt.algorithms import ECAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import binascii

from .nilql_wrapper import NilQLWrapper


class SecretVaultWrapper:
    def __init__(
        self,
        nodes: List[Dict[str, str]],
        credentials: Dict[str, str],
        schema_id: str = None,
        operation: str = "store",
        token_expiry_seconds: int = 3600,
    ):
        """
        :param nodes: List of dictionaries with at least "url" and "did" keys for each node.
        :param credentials: Dictionary with credentials (e.g. {"org_did": "...", "secret_key": "..."})
        :param schema_id: (Optional) Schema ID to be used.
        :param operation: Operation to be performed (default "store").
        :param token_expiry_seconds: Token validity in seconds.
        """
        self.nodes = nodes
        self.nodes_jwt = None
        self.credentials = credentials
        self.schema_id = schema_id
        self.operation = operation
        self.token_expiry_seconds = token_expiry_seconds
        self.nilql_wrapper = None

        # Registra o algoritmo ES256K
        self._register_es256k()

    def _hex_to_private_key(self, hex_key: str) -> str:
        """
        Converts a hexadecimal private key to PEM format.
        """
        try:
            # Remove '0x' prefix if it exists
            hex_key = hex_key.replace("0x", "")

            # Convert hex to bytes
            key_bytes = binascii.unhexlify(hex_key)

            # Load private key
            private_key = ec.derive_private_key(
                int.from_bytes(key_bytes, byteorder="big"), ec.SECP256K1()
            )

            # Serialize to PEM
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            return pem.decode("utf-8")

        except Exception as e:
            print(f"Error converting hex key to PEM: {str(e)}")
            raise

    def _register_es256k(self):
        """
        Registers the ES256K algorithm for use with PyJWT
        """
        try:
            jwt.unregister_algorithm("ES256K")
            jwt.register_algorithm("ES256K", ECAlgorithm(ECAlgorithm.SHA256))
        except Exception as e:
            print(f"Warning when registering ES256K algorithm: {str(e)}")

    async def init(self) -> NilQLWrapper:
        """
        Initializes the SecretVaultWrapper:
         - Generates tokens for nodes.
         - Instantiates and initializes NilQLWrapper with cluster configuration.
        :returns: Initialized NilQLWrapper instance.
        """
        node_configs = []
        for node in self.nodes:
            token = await self.generate_node_token(node["did"])
            node_configs.append({"url": node["url"], "jwt": token})
        self.nodes_jwt = node_configs

        # Instancia o NilQLWrapper com a configuração do cluster (usando os nós)
        self.nilql_wrapper = NilQLWrapper({"nodes": self.nodes}, self.operation)
        await self.nilql_wrapper.init()  # Gera a chave (secret ou cluster) conforme definido
        return self.nilql_wrapper

    def set_schema_id(self, schema_id: str, operation: str = None):
        """
        Updates the schema_id and, optionally, the operation.
        """
        self.schema_id = schema_id
        if operation is not None:
            self.operation = operation

    async def generate_node_token(self, node_did: str) -> str:
        """
        Generates a JWT token for node authentication using ES256K.
        """
        payload = {
            "iss": self.credentials["org_did"],
            "aud": node_did,
            "exp": int(time.time()) + self.token_expiry_seconds,
        }

        try:
            # Converte a chave hex para PEM
            private_key_pem = self._hex_to_private_key(self.credentials["secret_key"])

            # Gera o token com a chave PEM
            token = jwt.encode(payload, private_key_pem, algorithm="ES256K")

            if isinstance(token, bytes):
                token = token.decode("utf-8")

            return token

        except Exception as e:
            print(f"Erro ao gerar token: {str(e)}")
            raise

    async def generate_tokens_for_all_nodes(self) -> List[Dict[str, str]]:
        """
        Generates tokens for all nodes.
        """
        tokens = []
        for node in self.nodes:
            token = await self.generate_node_token(node["did"])
            tokens.append({"node": node["url"], "token": token})
        return tokens

    async def make_request(
        self,
        node_url: str,
        endpoint: str,
        token: str,
        payload: Dict[str, Any],
        method: str = "POST",
    ) -> Dict[str, Any]:
        """
        Makes an HTTP request to the node endpoint.
        """
        url = f"{node_url}/api/v1/{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=payload)
                else:
                    response = await client.request(
                        method.upper(), url, headers=headers, json=payload
                    )

                if not (200 <= response.status_code < 300):
                    raise Exception(
                        f"HTTP error! status: {response.status_code}, body: {response.text}"
                    )

                return response.json()
            except httpx.RequestError as e:
                raise Exception(f"Request failed: {str(e)}")

    async def allot_data(self, data: List[Dict[str, Any]]) -> List[Any]:
        """
        Transforms (e.g., encrypts) the data, preparing it for distribution.
        """
        encrypted_records = []
        for item in data:
            encrypted_item = await self.nilql_wrapper.prepare_and_allot(item)
            encrypted_records.append(encrypted_item)
        return encrypted_records

    async def flush_data(self) -> List[Dict[str, Any]]:
        """
        Clears data from all nodes for the current schema.
        """
        results = []
        for node in self.nodes:
            jwt_token = await self.generate_node_token(node["did"])
            payload = {"schema": self.schema_id}
            result = await self.make_request(
                node["url"], "data/flush", jwt_token, payload
            )
            results.append({"node": node["url"], "result": result})
        return results

    async def get_schemas(self) -> List[Any]:
        """
        Lists schemas from all nodes.
        """
        results = []
        for node in self.nodes:
            jwt_token = await self.generate_node_token(node["did"])
            result = await self.make_request(
                node["url"], "schemas", jwt_token, {}, method="GET"
            )
            results.append({"node": node["url"], "result": result})
        # Extracts the "data" field from each response.
        return [res["result"].get("data") for res in results]

    async def create_schema(
        self, schema: Dict[str, Any], schema_name: str, schema_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Creates a new schema in all nodes.
        """
        if not schema_id:
            schema_id = str(uuid.uuid4())
        schema_payload = {
            "_id": schema_id,
            "name": schema_name,
            "keys": ["_id"],
            "schema": schema,
        }
        results = []
        for node in self.nodes:
            jwt_token = await self.generate_node_token(node["did"])
            result = await self.make_request(
                node["url"], "schemas", jwt_token, schema_payload
            )
            results.append({"node": node["url"], "result": result})
        return results

    async def delete_schema(self, schema_id: str) -> List[Dict[str, Any]]:
        """
        Remove um schema de todos os nós.
        """
        results = []
        for node in self.nodes:
            jwt_token = await self.generate_node_token(node["did"])
            result = await self.make_request(
                node["url"], "schemas", jwt_token, {"id": schema_id}, method="DELETE"
            )
            results.append({"node": node["url"], "result": result})
        return results

    async def write_to_nodes(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Writes data to all nodes, applying field encryption if necessary.
        """
        # Adds an _id field to each record if it doesn't exist
        id_data = []
        for record in data:
            if "_id" not in record:
                new_record = record.copy()
                new_record["_id"] = str(uuid.uuid4())
                id_data.append(new_record)
            else:
                id_data.append(record)

        transformed_data = await self.allot_data(id_data)
        results = []

        for i, node in enumerate(self.nodes):
            try:
                node_data = []
                for encrypted_shares in transformed_data:
                    if len(encrypted_shares) != len(self.nodes):
                        node_data.append(encrypted_shares[0])
                    else:
                        node_data.append(encrypted_shares[i])
                jwt_token = await self.generate_node_token(node["did"])
                payload = {"schema": self.schema_id, "data": node_data}
                result = await self.make_request(
                    node["url"], "data/create", jwt_token, payload
                )
                results.append({"node": node["url"], "result": result})
            except Exception as e:
                print(f"❌ Failed to write to {node['url']}: {str(e)}")
                results.append({"node": node["url"], "error": str(e)})
        return results

    async def read_from_nodes(
        self, filter: Dict[str, Any] = {}
    ) -> List[Dict[str, Any]]:
        """
        Reads data from all nodes and then recombines the shares to form the original records.
        """
        results_from_all_nodes = []

        for node in self.nodes:
            try:
                jwt_token = await self.generate_node_token(node["did"])
                payload = {"schema": self.schema_id, "filter": filter}
                result = await self.make_request(
                    node["url"], "data/read", jwt_token, payload
                )
                results_from_all_nodes.append(
                    {"node": node["url"], "data": result.get("data", [])}
                )
            except Exception as e:
                print(f"❌ Failed to read from {node['url']}: {str(e)}")
                results_from_all_nodes.append({"node": node["url"], "error": str(e)})

        # Groups records from different nodes by _id field
        record_groups = []
        for node_result in results_from_all_nodes:
            for record in node_result.get("data", []):
                # Procura um grupo que já contenha um registro com o mesmo _id.
                group = next(
                    (
                        g
                        for g in record_groups
                        if any(
                            share.get("_id") == record.get("_id")
                            for share in g["shares"]
                        )
                    ),
                    None,
                )
                if group:
                    group["shares"].append(record)
                else:
                    record_groups.append(
                        {"shares": [record], "record_index": record.get("_id")}
                    )

        recombined_records = []
        for group in record_groups:
            recombined = await self.nilql_wrapper.unify(group["shares"])
            recombined_records.append(recombined)
        return recombined_records


# Usage example:
# (To test, make sure you have valid nodes and credentials, and adjust NilQLWrapper if needed.)
if __name__ == "__main__":

    async def main():
        nodes = [
            {"url": "https://node1.example.com", "did": "did:example:node1"},
            {"url": "https://node2.example.com", "did": "did:example:node2"},
            # Add other nodes as needed
        ]
        credentials = {
            "org_did": "did:example:org",
            "secret_key": "a1b2c3d4e5f60718293a4b5c6d7e8f90",  # Example (in hex)
        }
        schema_id = "schema-123"

        vault = SecretVaultWrapper(nodes, credentials, schema_id)
        await vault.init()

        # Example: write data to nodes.
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        write_results = await vault.write_to_nodes(data)
        print("Write results:", write_results)

        # Example: read data from nodes.
        read_results = await vault.read_from_nodes()
        print("Read results:", read_results)

    asyncio.run(main())
