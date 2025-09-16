"""
Blockchain in Supply Chain Management
Single-file end-to-end demo for Visual Studio Code

Run:
    1) Create virtualenv (recommended):
       python -m venv venv
       source venv/bin/activate   # Linux/Mac
       venv\Scripts\activate      # Windows

    2) Install requirements:
       pip install -r requirements.txt

    3) Run the app:
       python blockchain_supply_chain.py

    4) Open API docs in terminal output (Flask routes, examples using curl are below).
"""

import hashlib
import json
import time
import threading
from uuid import uuid4
from flask import Flask, request, jsonify, send_file
from urllib.parse import urlparse
import os

# ---------------------
# Configuration
# ---------------------
CHAIN_FILE = "chain_data.json"  # persistent storage of chain and pending txs
DIFFICULTY = 3                  # proof-of-work difficulty (number of leading zeros)
HOST = "127.0.0.1"
PORT = 5000

# ---------------------
# Blockchain core classes
# ---------------------
class Block:
    def __init__(self, index, timestamp, transactions, previous_hash, nonce=0):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions  # list of dicts
        self.previous_hash = previous_hash
        self.nonce = nonce

    def compute_hash(self):
        block_string = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(block_string.encode()).hexdigest()

class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.nodes = set()
        self.load_chain()

        if not self.chain:
            # create genesis block
            genesis_block = Block(index=0, timestamp=time.time(), transactions=[{"genesis": True}], previous_hash="0", nonce=0)
            genesis_block.hash = genesis_block.compute_hash()
            self.chain.append(genesis_block)
            self.save_chain()

    def new_transaction(self, transaction):
        """
        transaction: dict with keys:
         - tx_id (str, optional)
         - type (create|ship|receive|transfer)
         - product_id
         - from (participant id or None for create)
         - to (participant id or None)
         - metadata (dict) optional
         - timestamp (float) optional
        """
        tx = dict(transaction)  # shallow copy
        if "tx_id" not in tx:
            tx["tx_id"] = str(uuid4())
        tx["timestamp"] = tx.get("timestamp", time.time())
        self.pending_transactions.append(tx)
        self.save_chain()
        return tx

    def add_block(self, block, proof):
        previous_hash = self.chain[-1].hash
        if previous_hash != block.previous_hash:
            return False
        if not self.is_valid_proof(block, proof):
            return False
        block.hash = proof
        self.chain.append(block)
        self.save_chain()
        return True

    def proof_of_work(self, block):
        block.nonce = 0
        computed_hash = block.compute_hash()
        while not computed_hash.startswith('0' * DIFFICULTY):
            block.nonce += 1
            computed_hash = block.compute_hash()
        return computed_hash

    def mine(self, miner_id=None):
        if not self.pending_transactions:
            return None
        # Create new block
        last_block = self.chain[-1]
        new_block = Block(index=last_block.index + 1,
                          timestamp=time.time(),
                          transactions=self.pending_transactions.copy(),
                          previous_hash=last_block.hash)
        proof = self.proof_of_work(new_block)
        added = self.add_block(new_block, proof)
        if added:
            # reward the miner with a transaction (optional)
            if miner_id:
                reward_tx = {
                    "tx_id": str(uuid4()),
                    "type": "reward",
                    "product_id": None,
                    "from": None,
                    "to": miner_id,
                    "metadata": {"reward": "mined_block", "block_index": new_block.index},
                    "timestamp": time.time()
                }
                self.pending_transactions = [reward_tx]
            else:
                self.pending_transactions = []
            self.save_chain()
            return new_block
        else:
            return None

    # -----------------------
    # Validation & utility
    # -----------------------
    def is_valid_proof(self, block, block_hash):
        return (block_hash.startswith('0' * DIFFICULTY) and block_hash == block.compute_hash())

    def is_chain_valid(self, chain):
        """
        Validate a chain (list of block dicts)
        """
        if not chain:
            return False
        last_block = None
        for idx, block_dict in enumerate(chain):
            # reconstruct minimal block object
            block = Block(block_dict['index'], block_dict['timestamp'], block_dict['transactions'], block_dict['previous_hash'], block_dict.get('nonce', 0))
            computed_hash = block_dict.get('hash', None) or block.compute_hash()
            # genesis
            if idx == 0:
                # skip strict checks for genesis other than hash matching
                last_block = block
                last_block.hash = computed_hash
                continue
            # check previous hash
            if block.previous_hash != last_block.hash:
                return False
            # check proof
            if not self.is_valid_proof(block, computed_hash):
                return False
            block.hash = computed_hash
            last_block = block
        return True

    def get_product_history(self, product_id):
        history = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("product_id") == product_id:
                    history.append({
                        "block_index": block.index,
                        "tx": tx,
                        "timestamp": tx.get("timestamp")
                    })
        # also check pending txs
        for tx in self.pending_transactions:
            if tx.get("product_id") == product_id:
                history.append({
                    "block_index": None,
                    "tx": tx,
                    "timestamp": tx.get("timestamp")
                })
        return sorted(history, key=lambda x: x["timestamp"] or 0)

    def get_participant_history(self, participant_id):
        history = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("from") == participant_id or tx.get("to") == participant_id:
                    history.append({"block_index": block.index, "tx": tx})
        for tx in self.pending_transactions:
            if tx.get("from") == participant_id or tx.get("to") == participant_id:
                history.append({"block_index": None, "tx": tx})
        return history

    def save_chain(self):
        data = {
            "chain": [self._block_to_dict(b) for b in self.chain],
            "pending_transactions": self.pending_transactions
        }
        with open(CHAIN_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load_chain(self):
        if not os.path.exists(CHAIN_FILE):
            self.chain = []
            self.pending_transactions = []
            return
        with open(CHAIN_FILE, "r") as f:
            data = json.load(f)
        chain_list = []
        for bdict in data.get("chain", []):
            b = Block(bdict['index'], bdict['timestamp'], bdict['transactions'], bdict['previous_hash'], bdict.get('nonce', 0))
            b.hash = bdict.get('hash', b.compute_hash())
            chain_list.append(b)
        self.chain = chain_list
        self.pending_transactions = data.get("pending_transactions", [])

    def _block_to_dict(self, block):
        return {
            "index": block.index,
            "timestamp": block.timestamp,
            "transactions": block.transactions,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce,
            "hash": getattr(block, "hash", None)
        }

# ---------------------
# Flask API
# ---------------------
app = Flask(__name__)
node_identifier = str(uuid4()).replace('-', '')  # unique id for this node
blockchain = Blockchain()

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong", "node_id": node_identifier})

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    required = ["type", "product_id"]
    if not values:
        return jsonify({"error": "No data provided"}), 400
    for r in required:
        if r not in values:
            return jsonify({"error": f"Missing field: {r}"}), 400
    tx = blockchain.new_transaction(values)
    return jsonify({"message": "Transaction will be added", "transaction": tx}), 201

@app.route('/mine', methods=['POST'])
def mine():
    values = request.get_json() or {}
    miner_id = values.get("miner_id", node_identifier)
    block = blockchain.mine(miner_id=miner_id)
    if not block:
        return jsonify({"message": "No transactions to mine"}), 200
    response = {
        "message": "New Block Forged",
        "index": block.index,
        "transactions": block.transactions,
        "previous_hash": block.previous_hash,
        "hash": block.hash,
        "nonce": block.nonce
    }
    return jsonify(response), 200

@app.route('/chain', methods=['GET'])
def full_chain():
    chain_data = [blockchain._block_to_dict(b) for b in blockchain.chain]
    return jsonify({"chain": chain_data, "length": len(chain_data)}), 200

@app.route('/pending', methods=['GET'])
def pending_txs():
    return jsonify({"pending_transactions": blockchain.pending_transactions}), 200

@app.route('/product/<product_id>/history', methods=['GET'])
def product_history(product_id):
    history = blockchain.get_product_history(product_id)
    return jsonify({"product_id": product_id, "history": history}), 200

@app.route('/participant/<participant_id>/history', methods=['GET'])
def participant_history(participant_id):
    history = blockchain.get_participant_history(participant_id)
    return jsonify({"participant_id": participant_id, "history": history}), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get("nodes")
    if nodes is None:
        return jsonify({"error": "Please supply a list of nodes"}), 400
    for node in nodes:
        parsed = urlparse(node)
        blockchain.nodes.add(parsed.netloc or parsed.path)
    return jsonify({"message": "New nodes added", "total_nodes": list(blockchain.nodes)}), 201

@app.route('/nodes/resolve', methods=['POST'])
def consensus():
    """
    Expect JSON: { "chain": <list-of-block-dicts> }
    If the provided chain is longer and valid, replace local chain.
    This is a simple mechanism to demonstrate conflict resolution in a P2P setting.
    """
    values = request.get_json()
    external_chain = values.get("chain")
    if not external_chain:
        return jsonify({"error": "Provide a chain to compare"}), 400
    if len(external_chain) <= len(blockchain.chain):
        return jsonify({"message": "Local chain is longer or equal; no replacement"}), 200
    if blockchain.is_chain_valid(external_chain):
        # replace
        new_chain = []
        for bdict in external_chain:
            b = Block(bdict['index'], bdict['timestamp'], bdict['transactions'], bdict['previous_hash'], bdict.get('nonce', 0))
            b.hash = bdict.get('hash', b.compute_hash())
            new_chain.append(b)
        blockchain.chain = new_chain
        blockchain.save_chain()
        return jsonify({"message": "Chain replaced"}), 200
    else:
        return jsonify({"message": "External chain invalid"}), 400

@app.route('/export', methods=['GET'])
def export_chain_file():
    # Download the chain file for submission
    if os.path.exists(CHAIN_FILE):
        return send_file(CHAIN_FILE, as_attachment=True)
    else:
        return jsonify({"error": "No chain file found"}), 404

# ---------------------
# Helper: Demo data creation
# ---------------------
def create_demo_data():
    """
    Create sample participants and product events for demonstration.
    Participant ids are simple strings (e.g., 'manufacturer_1')
    Product ids are strings like 'prod-0001'
    """
    # Only add demo if chain is small
    if len(blockchain.chain) > 1 or blockchain.pending_transactions:
        return

    demo_participants = ["manufacturer_1", "transporter_1", "warehouse_1", "retailer_1"]
    # Create product
    prod_id = "prod-0001"
    tx1 = {
        "type": "create",
        "product_id": prod_id,
        "from": None,
        "to": demo_participants[0],
        "metadata": {"name": "Organic Apples", "batch": "BATCH-42", "quantity": 100}
    }
    blockchain.new_transaction(tx1)

    # Ship from manufacturer to transporter
    tx2 = {
        "type": "ship",
        "product_id": prod_id,
        "from": demo_participants[0],
        "to": demo_participants[1],
        "metadata": {"eta_hours": 10, "transport_mode": "truck"}
    }
    blockchain.new_transaction(tx2)

    # Receive at warehouse
    tx3 = {
        "type": "receive",
        "product_id": prod_id,
        "from": demo_participants[1],
        "to": demo_participants[2],
        "metadata": {"condition": "good", "received_qty": 100}
    }
    blockchain.new_transaction(tx3)

    # Transfer to retailer
    tx4 = {
        "type": "transfer",
        "product_id": prod_id,
        "from": demo_participants[2],
        "to": demo_participants[3],
        "metadata": {"delivered_qty": 100}
    }
    blockchain.new_transaction(tx4)

    # Auto-mine demo block in background to persist the demo transactions
    def mine_later():
        time.sleep(1)
        blockchain.mine(miner_id="miner_demo")

    threading.Thread(target=mine_later).start()

# create demo data at startup if none exists
create_demo_data()

# ---------------------
# CLI entrypoint
# ---------------------
if __name__ == '__main__':
    print("Starting Blockchain Supply Chain node")
    print(f"Node ID: {node_identifier}")
    print(f"Chain file: {CHAIN_FILE}")
    print("Available endpoints:")
    print("  GET  /ping")
    print("  GET  /chain")
    print("  GET  /pending")
    print("  POST /transactions/new   JSON: {type, product_id, from, to, metadata}")
    print("  POST /mine              JSON: { miner_id (optional) }")
    print("  GET  /product/<id>/history")
    print("  GET  /participant/<id>/history")
    print("  POST /nodes/register    JSON: { nodes: [url1, url2...] }")
    print("  POST /nodes/resolve     JSON: { chain: [...] }")
    print("  GET  /export            download chain_data.json")
    print("\nExample curl commands (run in another terminal):")
    print("  curl -X GET http://127.0.0.1:5000/chain")
    print("  curl -H \"Content-Type: application/json\" -X POST -d '{\"type\":\"create\",\"product_id\":\"prod-0002\",\"from\":null,\"to\":\"manufacturer_1\",\"metadata\":{\"name\":\"Oranges\"}}' http://127.0.0.1:5000/transactions/new")
    print("  curl -X POST -H \"Content-Type: application/json\" -d '{\"miner_id\":\"miner1\"}' http://127.0.0.1:5000/mine")
    app.run(host=HOST, port=PORT, debug=True)
    