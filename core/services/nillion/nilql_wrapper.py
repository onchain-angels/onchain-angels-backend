import nilql


# Definindo um "enum" simples para os tipos de chave
class KeyType:
    CLUSTER = "cluster"
    SECRET = "secret"


class NilQLWrapper:
    def __init__(
        self, cluster, operation="store", secret_key=None, key_type=KeyType.CLUSTER
    ):
        """
        :param cluster: Configuration of the cluster (e.g., a dictionary containing nodes)
        :param operation: Desired operation (e.g., 'store')
        :param secret_key: (Optional) pre-generated secret key
        :param key_type: Type of key to be used ("cluster" or "secret")
        """
        self.cluster = cluster
        self.secret_key = secret_key
        self.operation = {operation: True}
        self.key_type = key_type

    async def init(self):
        """
        Inicializa o wrapper gerando (ou utilizando) a chave apropriada para o cluster.
        Deve ser chamado antes de qualquer operação de criptografia ou descriptografia.
        """
        if self.secret_key is None and self.key_type == KeyType.SECRET:
            self.secret_key = nilql.SecretKey.generate(self.cluster, self.operation)
        if self.key_type == KeyType.CLUSTER:
            self.secret_key = nilql.ClusterKey.generate(self.cluster, self.operation)

    async def encrypt(self, data):
        """
        Criptografa os dados utilizando a chave inicializada.
        Retorna os _shares_ criptografados.
        """
        if not self.secret_key:
            raise Exception("NilQLWrapper not initialized. Call init() first.")
        shares = nilql.encrypt(self.secret_key, data)
        return shares

    async def decrypt(self, shares):
        """
        Descriptografa os _shares_ utilizando a chave inicializada.
        """
        if not self.secret_key:
            raise Exception("NilQLWrapper not initialized. Call init() first.")
        decryptedData = nilql.decrypt(self.secret_key, shares)
        return decryptedData

    async def prepare_and_allot(self, data):
        """
        Recursively traverses the input object and, for each field containing the "$allot" key,
        encrypts the associated value and prepares the document for share distribution.
        """
        if not self.secret_key:
            raise Exception("NilQLWrapper not initialized. Call init() first.")

        async def encrypt_deep(obj):
            if not isinstance(obj, dict):
                return obj

            encrypted = {}
            for key, value in obj.items():
                if isinstance(value, dict):
                    if "$allot" in value:
                        encrypted_value = await self.encrypt(value["$allot"])
                        encrypted[key] = {"$allot": encrypted_value}
                    else:
                        encrypted[key] = await encrypt_deep(value)
                elif isinstance(value, list):
                    encrypted[key] = []
                    for item in value:
                        if isinstance(item, (dict, list)):
                            encrypted_item = await encrypt_deep(item)
                            encrypted[key].append(encrypted_item)
                        else:
                            encrypted[key].append(item)
                else:
                    encrypted[key] = value
            return encrypted

        encrypted_data = await encrypt_deep(data)
        return nilql.allot(encrypted_data)

    async def unify(self, shares):
        """
        Recombina os _shares_ para reconstruir o documento original (descriptografado).
        """
        if not self.secret_key:
            raise Exception("NilQLWrapper not initialized. Call init() first.")
        unifiedResult = nilql.unify(self.secret_key, shares)
        return unifiedResult
