# Complete MetaAPI Technical Reference

## Table of Contents

- [Complete MetaAPI Technical Reference](#complete-metaapi-technical-reference)
  - [Table of Contents](#table-of-contents)
  - [Core API Components](#core-api-components)
    - [MetaApi](#metaapi)
    - [MetatraderAccountApi](#metatraderaccountapi)
    - [ProvisioningProfileApi](#provisioningprofileapi)
  - [Connection Management](#connection-management)
    - [ConnectionRegistry](#connectionregistry)
    - [StreamingMetaApiConnection](#streamingmetaapiconnection)
    - [RpcMetaApiConnection](#rpcmetaapiconnection)
  - [Trading Operations](#trading-operations)
    - [Trade Methods](#trade-methods)
  - [Market Data Operations](#market-data-operations)
    - [Market Data Methods](#market-data-methods)
    - [Historical Data Methods](#historical-data-methods)
  - [Account Management](#account-management)
    - [MetatraderAccount](#metatraderaccount)
    - [MetatraderAccountReplica](#metatraderaccountreplica)
  - [Expert Advisors](#expert-advisors)
  - [History \& Storage](#history--storage)
    - [HistoryStorage](#historystorage)
    - [MemoryHistoryStorage](#memoryhistorystorage)
    - [FilesystemHistoryDatabase](#filesystemhistorydatabase)
  - [Token Management](#token-management)
    - [TokenManagementApi](#tokenmanagementapi)
  - [Monitoring \& Statistics](#monitoring--statistics)
    - [LatencyMonitor](#latencymonitor)
    - [ConnectionHealthMonitor](#connectionhealthmonitor)
    - [Statistical Analysis](#statistical-analysis)
  - [Terminal State Management](#terminal-state-management)
    - [TerminalState](#terminalstate)
  - [Data Structures](#data-structures)
    - [Account Related](#account-related)
    - [Trading Related](#trading-related)
  - [Market Data Structures](#market-data-structures)
    - [Price \& Quote Data](#price--quote-data)
    - [Symbol Specifications](#symbol-specifications)
  - [Error Handling](#error-handling)
    - [Exception Classes](#exception-classes)
    - [Error Response Structures](#error-response-structures)
  - [Configuration](#configuration)
    - [Connection Options](#connection-options)
    - [Retry Configuration](#retry-configuration)
    - [Synchronization Options](#synchronization-options)
  - [Advanced Features](#advanced-features)
    - [Hash Management](#hash-management)
    - [ReferenceTree](#referencetree)
    - [Performance Monitoring](#performance-monitoring)
    - [Reservoir Statistics](#reservoir-statistics)
  - [WebSocket Client Options](#websocket-client-options)
- [MetaAPI Cloud SDK API Documentation](#metaapi-cloud-sdk-api-documentation)
  - [初始化和连接管理](#初始化和连接管理)
  - [市场数据API](#市场数据api)
    - [1. K线数据](#1-k线数据)
    - [2. Tick数据](#2-tick数据)
    - [3. 订单簿数据](#3-订单簿数据)
    - [4. 市场信息查询](#4-市场信息查询)
    - [5. 订阅管理](#5-订阅管理)
  - [完整的流数据处理示例](#完整的流数据处理示例)
  - [错误处理和连接管理](#错误处理和连接管理)
- [重试选项](#重试选项)
- [连接状态管理](#连接状态管理)
- [连接状态检查](#连接状态检查)
- [获取连接健康状态](#获取连接健康状态)
- [等待特定状态](#等待特定状态)
- [获取服务器时间](#获取服务器时间)
- [获取账户信息](#获取账户信息)
- [资源清理](#资源清理)

## Core API Components

### MetaApi
```python
class MetaApi:
    def __init__(self, token: str, opts: MetaApiOpts = None):
        """Initialize MetaApi instance
        
        Args:
            token: API access token
            opts: API options
        """
        
    @property
    def metatrader_account_api(self) -> MetatraderAccountApi:
        """Returns MetaTrader account API"""
        
    @property
    def provisioning_profile_api(self) -> ProvisioningProfileApi:
        """Returns provisioning profile API"""
        
    @property
    def metatrader_account_generator_api(self) -> MetatraderAccountGeneratorApi:
        """Returns account generator API"""
        
    @property
    def latency_monitor(self) -> LatencyMonitor:
        """Returns latency monitor"""
        
    @property
    def token_management_api(self) -> TokenManagementApi:
        """Returns token management API"""
        
    def close(self):
        """Closes all connections"""

    @staticmethod
    def enable_logging():
        """Enables extended logging"""

    @staticmethod
    def format_error(err: Exception):
        """Formats error with additional info"""
```

### MetatraderAccountApi
```python
class MetatraderAccountApi:
    async def get_accounts_with_infinite_scroll_pagination(
        self, accounts_filter: AccountsFilter = None
    ) -> List[MetatraderAccount]:
        """Returns trading accounts with infinite scroll pagination"""
        
    async def get_accounts_with_classic_scroll_pagination(
        self, accounts_filter: AccountsFilter = None
    ) -> List[MetatraderAccountList]:
        """Returns trading accounts with classic pagination"""
        
    async def get_account(self, account_id: str) -> MetatraderAccount:
        """Returns trading account by id"""
        
    async def get_account_replica(
        self, account_id: str, replica_id: str
    ) -> MetatraderAccountReplica:
        """Returns trading account replica"""
        
    async def create_account(
        self, account: NewMetatraderAccountDto
    ) -> MetatraderAccount:
        """Creates new trading account"""
```

### ProvisioningProfileApi
```python
class ProvisioningProfileApi:
    async def get_provisioning_profiles_with_infinite_scroll_pagination(
        self, filter: ProvisioningProfilesFilter = None
    ) -> List[ProvisioningProfile]:
        """Retrieves provisioning profiles with infinite scroll"""
        
    async def get_provisioning_profile(
        self, provisioning_profile_id: str
    ) -> ProvisioningProfile:
        """Retrieves provisioning profile by id"""
        
    async def create_provisioning_profile(
        self, profile: NewProvisioningProfileDto
    ) -> ProvisioningProfile:
        """Creates new provisioning profile"""
```

## Connection Management

### ConnectionRegistry
```python
class ConnectionRegistry:
    def connect_streaming(
        self,
        account: MetatraderAccountModel,
        history_storage: HistoryStorage,
        history_start_time: datetime = None
    ) -> StreamingMetaApiConnectionInstance:
        """Creates streaming connection"""
        
    def connect_rpc(
        self, account: MetatraderAccountModel
    ) -> RpcMetaApiConnectionInstance:
        """Creates RPC connection"""
        
    async def remove_streaming(self, account: MetatraderAccountModel):
        """Removes streaming connection"""
        
    async def remove_rpc(self, account: MetatraderAccountModel):
        """Removes RPC connection"""
        
    def remove(self, account_id: str):
        """Removes account from registry"""
```

### StreamingMetaApiConnection
```python
class StreamingMetaApiConnection:
    async def connect(self, instance_id: str):
        """Opens connection"""
        
    async def close(self, instance_id: str):
        """Closes connection"""
        
    async def subscribe_to_market_data(
        self,
        symbol: str,
        subscriptions: List[MarketDataSubscription] = None,
        timeout_in_seconds: float = None,
        wait_for_quote: bool = True
    ):
        """Subscribes to market data"""
        
    async def unsubscribe_from_market_data(
        self,
        symbol: str,
        unsubscriptions: List[MarketDataUnsubscription] = None
    ):
        """Unsubscribes from market data"""
        
    @property
    def subscribed_symbols(self) -> List[str]:
        """Returns subscribed symbols"""
        
    @property
    def terminal_state(self) -> TerminalState:
        """Returns terminal state"""
        
    @property
    def history_storage(self) -> HistoryStorage:
        """Returns history storage"""
        
    @property
    def synchronized(self) -> bool:
        """Returns synchronization status"""
```

### RpcMetaApiConnection
```python
class RpcMetaApiConnection:
    async def connect(self, instance_id: str):
        """Opens connection"""
        
    async def close(self, instance_id: str):
        """Closes connection"""
        
    async def wait_synchronized(self, timeout_in_seconds: float = 300):
        """Waits for synchronization"""
        
    @property
    def synchronized(self) -> bool:
        """Returns synchronization status"""
```

## Trading Operations

### Trade Methods
```python
async def create_market_buy_order(
    symbol: str,
    volume: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: CreateMarketTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates market buy order"""

async def create_market_sell_order(
    symbol: str,
    volume: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: CreateMarketTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates market sell order"""

async def create_limit_buy_order(
    symbol: str,
    volume: float,
    open_price: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: PendingTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates limit buy order"""

async def create_limit_sell_order(
    symbol: str,
    volume: float,
    open_price: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: PendingTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates limit sell order"""

async def create_stop_buy_order(
    symbol: str,
    volume: float,
    open_price: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: PendingTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates stop buy order"""

async def create_stop_sell_order(
    symbol: str,
    volume: float,
    open_price: float,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    options: PendingTradeOptions = None
) -> MetatraderTradeResponse:
    """Creates stop sell order"""

async def modify_position(
    position_id: str,
    stop_loss: Union[float, StopOptions] = None,
    take_profit: Union[float, StopOptions] = None,
    trailing_stop_loss: str = None
) -> MetatraderTradeResponse:
    """Modifies position"""

async def close_position(
    position_id: str,
    options: MarketTradeOptions = None
) -> MetatraderTradeResponse:
    """Closes position"""

async def close_by(
    position_id: str,
    opposite_position_id: str,
    options: MarketTradeOptions = None
) -> MetatraderTradeResponse:
    """Closes position by opposite one"""

async def close_positions_by_symbol(
    symbol: str,
    options: MarketTradeOptions = None
) -> MetatraderTradeResponse:
    """Closes positions by symbol"""
```

## Market Data Operations

### Market Data Methods
```python
async def get_symbol_price(
    symbol: str,
    keep_subscription: bool = False
) -> MetatraderSymbolPrice:
    """Returns latest symbol price
    
    Args:
        symbol: Symbol to get price for
        keep_subscription: Whether to maintain long-term subscription
    """

async def get_symbol_specification(
    symbol: str
) -> MetatraderSymbolSpecification:
    """Returns symbol specification"""

async def get_candle(
    symbol: str,
    timeframe: str,
    keep_subscription: bool = False
) -> MetatraderCandle:
    """Returns latest candle
    
    Args:
        symbol: Symbol to get candle for
        timeframe: Timeframe (e.g. '1m', '5m', '1h')
        keep_subscription: Whether to maintain long-term subscription
    """

async def get_tick(
    symbol: str,
    keep_subscription: bool = False
) -> MetatraderTick:
    """Returns latest tick"""

async def get_book(
    symbol: str,
    keep_subscription: bool = False
) -> MetatraderBook:
    """Returns order book"""

async def get_symbols(self) -> List[str]:
    """Returns available symbols"""
```

### Historical Data Methods
```python
async def get_historical_candles(
    self,
    symbol: str,
    timeframe: str,
    start_time: datetime = None,
    limit: int = None
) -> List[MetatraderCandle]:
    """Returns historical candles
    
    Args:
        symbol: Symbol to get history for
        timeframe: Timeframe (e.g. '1m', '5m', '1h')
        start_time: Start time for history
        limit: Maximum number of candles
    """

async def get_historical_ticks(
    self,
    symbol: str,
    start_time: datetime = None,
    offset: int = None,
    limit: int = None
) -> List[MetatraderTick]:
    """Returns historical ticks"""

async def get_server_time(self) -> ServerTime:
    """Returns current server time"""
```

## Account Management

### MetatraderAccount
```python
class MetatraderAccount:
    @property
    def id(self) -> str:
        """Returns account id"""
    
    @property
    def name(self) -> str:
        """Returns account name"""
    
    @property
    def type(self) -> str:
        """Returns account type"""
    
    @property
    def login(self) -> str:
        """Returns account login"""
    
    @property
    def server(self) -> str:
        """Returns broker server"""
    
    @property
    def reliability(self) -> str:
        """Returns account reliability"""
    
    @property
    def region(self) -> str:
        """Returns account region"""
    
    async def deploy(self):
        """Deploys account"""
    
    async def undeploy(self):
        """Undeploys account"""
    
    async def redeploy(self):
        """Redeploys account"""
    
    async def increase_reliability(self):
        """Increases account reliability"""
    
    async def wait_connected(
        self,
        timeout_in_seconds: float = 300,
        interval_in_milliseconds: float = 1000
    ):
        """Waits until connected to broker"""
```

### MetatraderAccountReplica
```python
class MetatraderAccountReplica:
    @property
    def id(self) -> str:
        """Returns replica id"""
    
    @property
    def state(self) -> str:
        """Returns replica state"""
    
    @property
    def magic(self) -> int:
        """Returns magic number"""
    
    @property
    def connection_status(self) -> str:
        """Returns connection status"""
    
    async def deploy(self):
        """Deploys replica"""
    
    async def undeploy(self):
        """Undeploys replica"""
    
    async def redeploy(self):
        """Redeploys replica"""
    
    async def update(self, replica: UpdatedMetatraderAccountReplicaDto):
        """Updates replica configuration"""
```

## Expert Advisors

```python
class ExpertAdvisor:
    @property
    def expert_id(self) -> str:
        """Returns expert id"""
    
    @property
    def period(self) -> str:
        """Returns expert period"""
    
    @property
    def symbol(self) -> str:
        """Returns expert symbol"""
    
    @property
    def file_uploaded(self) -> bool:
        """Returns true if expert file was uploaded"""
    
    async def reload(self):
        """Reloads expert advisor from API"""
    
    async def update(self, expert: NewExpertAdvisorDto):
        """Updates expert advisor configuration"""
    
    async def upload_file(self, file: Union[str, memoryview]):
        """Uploads expert advisor file"""
    
    async def remove(self):
        """Removes expert advisor"""

class ExpertAdvisorClient:
    async def get_expert_advisors(self, account_id: str) -> List[ExpertAdvisor]:
        """Returns account's expert advisors"""
    
    async def get_expert_advisor(
        self, 
        account_id: str, 
        expert_id: str
    ) -> ExpertAdvisor:
        """Returns specific expert advisor"""
    
    async def update_expert_advisor(
        self,
        account_id: str,
        expert_id: str,
        expert: NewExpertAdvisorDto
    ):
        """Updates expert advisor"""
```

## History & Storage

### HistoryStorage
```python
class HistoryStorage:
    async def initialize(self, account_id: str, application: str):
        """Initializes storage"""
    
    async def clear(self):
        """Clears storage"""
    
    async def last_history_order_time(self, instance_index: str = None) -> datetime:
        """Returns last history order time"""
    
    async def last_deal_time(self, instance_index: str = None) -> datetime:
        """Returns last deal time"""
    
    @property
    def deals(self) -> List[MetatraderDeal]:
        """Returns all deals"""
    
    def get_deals_by_ticket(self, id: str) -> List[MetatraderDeal]:
        """Returns deals by ticket"""
    
    def get_deals_by_position(self, position_id: str) -> List[MetatraderDeal]:
        """Returns deals by position"""
    
    @property
    def history_orders(self) -> List[MetatraderOrder]:
        """Returns historical orders"""
    
    def get_history_orders_by_ticket(self, id: str) -> List[MetatraderOrder]:
        """Returns history orders by ticket"""
```

### MemoryHistoryStorage
```python
class MemoryHistoryStorage(HistoryStorageModel):
    def __init__(self):
        """Initializes memory history storage"""
    
    async def on_history_order_added(
        self,
        instance_index: str,
        history_order: MetatraderOrder
    ):
        """Processes new history order"""
    
    async def on_deal_added(self, instance_index: str, deal: MetatraderDeal):
        """Processes new deal"""
```

### FilesystemHistoryDatabase
```python
class FilesystemHistoryDatabase:
    async def load_history(self, account_id: str, application: str):
        """Loads history from database"""
    
    async def clear(self, account_id: str, application: str):
        """Clears history"""
    
    async def flush(
        self,
        account_id: str,
        application: str,
        new_history_orders: List[MetatraderOrder],
        new_deals: List[MetatraderDeal]
    ):
        """Flushes new history to database"""
```
## Token Management

### TokenManagementApi
```python
class TokenManagementApi:
    async def get_access_rules(self) -> List[ManifestAccessRule]:
        """Gets access rules manifest"""
    
    async def narrow_down_token(
        self,
        narrow_down_payload: Union[NarrowDownAccessRules, NarrowDownSimplifiedAccessRules],
        validity_in_hours: float = None
    ) -> str:
        """Returns narrowed down token
        
        Args:
            narrow_down_payload: Access rules configuration
            validity_in_hours: Token validity period
        """
    
    async def narrow_down_token_resources(
        self,
        resources: List[AccessRuleResource],
        validity_in_hours: float = None
    ) -> str:
        """Returns token with access to specific resources"""
    
    async def narrow_down_token_roles(
        self,
        roles: List[str],
        validity_in_hours: float = None
    ) -> str:
        """Returns token with specific roles"""
    
    async def narrow_down_token_applications(
        self,
        applications: List[str],
        validity_in_hours: float = None
    ) -> str:
        """Returns token with access to specific applications"""
    
    def are_token_resources_narrowed_down(self, token: str) -> bool:
        """Checks if token resources are restricted"""
```

## Monitoring & Statistics

### LatencyMonitor
```python
class LatencyMonitor(LatencyListener):
    async def on_response(
        self,
        account_id: str,
        type: str,
        timestamps: ResponseTimestamps
    ):
        """Processes response latency data"""
    
    async def on_symbol_price(
        self,
        account_id: str,
        symbol: str,
        timestamps: SymbolPriceTimestamps
    ):
        """Processes price latency data"""
    
    async def on_update(self, account_id: str, timestamps: UpdateTimestamps):
        """Processes update latency data"""
    
    async def on_trade(self, account_id: str, timestamps: TradeTimestamps):
        """Processes trade latency data"""
    
    @property
    def request_latencies(self) -> Dict:
        """Returns request processing latencies"""
    
    @property
    def price_latencies(self) -> Dict:
        """Returns price streaming latencies"""
    
    @property
    def update_latencies(self) -> Dict:
        """Returns update streaming latencies"""
    
    @property
    def trade_latencies(self) -> Dict:
        """Returns trade latencies"""
```

### ConnectionHealthMonitor
```python
class ConnectionHealthMonitor:
    def __init__(self, connection):
        """Initializes health monitor"""
    
    def stop(self):
        """Stops health monitor"""
    
    async def on_symbol_price_updated(
        self,
        instance_index: str,
        price: MetatraderSymbolPrice
    ):
        """Processes price update for health monitoring"""
    
    async def on_health_status(
        self,
        instance_index: str,
        status: HealthStatus
    ):
        """Processes health status update"""
    
    @property
    def health_status(self) -> ConnectionHealthStatus:
        """Returns current health status"""
    
    @property
    def uptime(self) -> dict:
        """Returns connection uptime statistics"""
```

### Statistical Analysis
```python
class Reservoir:
    def __init__(
        self,
        size: int,
        storage_period_in_milliseconds: int = 60000
    ):
        """Initializes measurement reservoir"""
    
    def push_measurement(self, data: float):
        """Adds measurement to reservoir"""
    
    def get_statistics(self) -> dict:
        """Returns reservoir statistics"""

class StatisticalReservoir:
    def __init__(
        self,
        size: int,
        interval: int,
        random_number_gen: Callable = None
    ):
        """Initializes statistical reservoir"""
    
    def push_measurement(self, data: float):
        """Adds measurement to reservoir"""
    
    def get_percentile(self, p: float):
        """Calculates percentile value"""
```

## Terminal State Management

### TerminalState
```python
class TerminalState:
    @property
    def connected(self) -> bool:
        """Returns connection status"""
    
    @property
    def connected_to_broker(self) -> bool:
        """Returns broker connection status"""
    
    @property
    def account_information(self) -> MetatraderAccountInformation:
        """Returns account information"""
    
    @property
    def positions(self) -> List[MetatraderPosition]:
        """Returns open positions"""
    
    @property
    def orders(self) -> List[MetatraderOrder]:
        """Returns pending orders"""
    
    @property
    def specifications(self) -> List[MetatraderSymbolSpecification]:
        """Returns symbol specifications"""
    
    def specification(self, symbol: str) -> MetatraderSymbolSpecification:
        """Returns specific symbol specification"""
    
    def price(self, symbol: str) -> MetatraderSymbolPrice:
        """Returns symbol price"""
    
    async def wait_for_price(
        self,
        symbol: str,
        timeout_in_seconds: float = 30
    ):
        """Waits for price to be received"""
    
    async def refresh_terminal_state(
        self,
        options: RefreshTerminalStateOptions = None
    ):
        """Forces refresh of terminal state"""
```

## Data Structures

### Account Related
```python
class MetatraderAccountInformation(TypedDict):
    platform: str          # Platform id (mt4/mt5)
    broker: str           # Broker name
    currency: str         # Account currency
    server: str           # Broker server
    balance: float        # Account balance
    equity: float         # Account equity
    margin: float         # Used margin
    freeMargin: float    # Free margin
    leverage: float      # Account leverage
    marginLevel: float   # Margin level percentage
    tradeAllowed: bool   # Trading allowed flag
    investorMode: bool   # Investor password used
    marginMode: str      # Margin calculation mode
```

### Trading Related
```python
class MetatraderPosition(TypedDict):
    id: int              # Position id
    type: str           # Position type (buy/sell)
    symbol: str         # Trading symbol
    magic: int          # Magic number
    time: datetime      # Open time
    brokerTime: str     # Broker timezone time
    updateTime: datetime # Last update time
    openPrice: float    # Open price
    currentPrice: float # Current price
    volume: float       # Position volume
    swap: float        # Accumulated swap
    profit: float      # Current profit
    comment: str       # Position comment
    clientId: str      # Client-defined id

class MetatraderOrder(TypedDict):
    id: int            # Order id
    type: str         # Order type
    state: str        # Order state
    magic: int        # Magic number
    symbol: str       # Trading symbol
    openPrice: float  # Order price
    volume: float    # Order volume
    currentVolume: float # Remaining volume
    positionId: str  # Related position id
    comment: str     # Order comment
```

## Market Data Structures

### Price & Quote Data
```python
class MetatraderSymbolPrice(TypedDict):
    symbol: str            # Trading symbol
    bid: float            # Bid price
    ask: float            # Ask price
    profitTickValue: float # Tick value for profitable positions
    lossTickValue: float  # Tick value for losing positions
    accountCurrencyExchangeRate: float # Account currency exchange rate
    time: datetime        # Quote time
    brokerTime: str      # Broker timezone time

class MetatraderTick(TypedDict):
    symbol: str          # Trading symbol
    time: datetime      # Tick time
    brokerTime: str     # Broker timezone time
    bid: Optional[float] # Bid price
    ask: Optional[float] # Ask price
    last: Optional[float] # Last deal price
    volume: float       # Deal volume
    side: str          # Deal side (buy/sell)

class MetatraderCandle(TypedDict):
    symbol: str         # Trading symbol
    timeframe: str      # Time period
    time: datetime     # Candle time
    brokerTime: str    # Broker timezone time
    open: float        # Open price
    high: float        # High price
    low: float         # Low price
    close: float       # Close price
    tickVolume: float  # Tick volume
    spread: float      # Spread
    volume: float      # Trade volume
```

### Symbol Specifications
```python
class MetatraderSymbolSpecification(TypedDict):
    symbol: str          # Symbol name
    tickSize: float      # Min price change
    minVolume: float     # Min trade volume
    maxVolume: float     # Max trade volume
    volumeStep: float    # Volume change step
    fillingModes: List[str] # Allowed filling modes
    executionMode: str   # Deal execution mode
    contractSize: float  # Trade contract size
    quoteSessions: MetatraderSessions  # Quote sessions
    tradeSessions: MetatraderSessions  # Trade sessions
    tradeMode: str       # Order execution type
    digits: int          # Price digits
    point: float         # Point size
    currency: str        # Symbol currency
    marginMode: str      # Margin calculation mode
```

## Error Handling

### Exception Classes
```python
class MetaApiException(Exception):
    """Base exception for MetaApi errors"""
    def __init__(self, message: str, status_code: int = None):
        self.status_code = status_code
        self.message = message

class NotFoundException(MetaApiException):
    """Resource not found error"""
    pass

class ValidationException(MetaApiException):
    """Validation error"""
    def __init__(self, message: str, details: List[ValidationDetails] = None):
        self.details = details

class TimeoutException(MetaApiException):
    """Operation timeout error"""
    pass

class TradeException(MetaApiException):
    """Trading operation error"""
    def __init__(self, message: str, string_code: str = None):
        self.string_code = string_code

class TooManyRequestsException(MetaApiException):
    """Rate limit exceeded error"""
    def __init__(self, message: str, metadata: Dict = None):
        self.metadata = metadata
```

### Error Response Structures
```python
class ValidationDetails(TypedDict):
    parameter: str       # Invalid parameter name
    value: Optional[str] # Invalid value
    message: str        # Error message

class ExceptionMessage(TypedDict):
    id: int             # Error id
    error: str          # Error name
    numericCode: int    # Error code
    stringCode: str     # String error code
    message: str        # Error message
    details: List[ValidationDetails]  # Validation details
```

## Configuration

### Connection Options
```python
class MetaApiOpts(TypedDict):
    application: Optional[str]  # Application id
    domain: Optional[str]      # Domain to connect to
    region: Optional[str]      # Region to connect to
    requestTimeout: Optional[float]  # Request timeout
    connectTimeout: Optional[float]  # Connection timeout
    packetOrderingTimeout: Optional[float]  # Packet ordering timeout
    packetLogger: Optional[PacketLoggerOpts]  # Logger options
    enableLatencyTracking: Optional[bool]  # Enable latency tracking
    synchronizationThrottler: Optional[SynchronizationThrottlerOpts]
    retryOpts: Optional[RetryOpts]  # Retry options
    useSharedClientApi: Optional[bool]  # Use shared server
    enableSocketioDebugger: Optional[bool]  # Enable debug mode
```

### Retry Configuration
```python
class RetryOpts(TypedDict):
    retries: Optional[int]  # Max retries count
    minDelayInSeconds: Optional[float]  # Min retry delay
    maxDelayInSeconds: Optional[float]  # Max retry delay
    longRunningRequestTimeoutInMinutes: Optional[float]
```

### Synchronization Options
```python
class SynchronizationOptions(TypedDict):
    instanceIndex: Optional[int]  # Account instance index
    applicationPattern: Optional[str]  # Application pattern
    synchronizationId: Optional[str]  # Sync request ID
    timeoutInSeconds: Optional[float]  # Wait timeout
    intervalInMilliseconds: Optional[float]  # Check interval
```

## Advanced Features

### Hash Management
```python
class TerminalHashManager:
    def get_specifications_by_hash(
        self,
        specification_hash: str
    ) -> Dict[str, MetatraderSymbolSpecification]:
        """Returns specifications by hash"""
    
    def get_positions_by_hash(
        self,
        positions_hash: str
    ) -> Dict[str, MetatraderPosition]:
        """Returns positions by hash"""
    
    def get_orders_by_hash(
        self,
        orders_hash: str
    ) -> Dict[str, MetatraderOrder]:
        """Returns orders by hash"""
```

### ReferenceTree
```python
class ReferenceTree:
    def get_items_by_hash(self, hash: str) -> Union[Dict[str, Dict], None]:
        """Returns data by hash"""
    
    def record_items(
        self,
        category_name: str,
        account_type: str,
        connection_id: str,
        instance_index: str,
        items: List
    ) -> Union[str, None]:
        """Records new items"""
    
    def get_last_used_hashes(self, category_name: str) -> List[str]:
        """Returns recently used hashes"""
```

### Performance Monitoring
```python
class LatencyService:
    def get_latencies(self) -> Dict:
        """Returns all latency measurements"""
    
    def get_trade_latencies(self) -> Dict:
        """Returns trade operation latencies"""
    
    def get_market_data_latencies(self) -> Dict:
        """Returns market data latencies"""

class ConnectionUptime:
    def measure_uptime(self):
        """Measures connection uptime"""
    
    def get_statistics(self) -> Dict:
        """Returns uptime statistics"""
```

### Reservoir Statistics
```python
class ReservoirStatistics(TypedDict):
    count: int          # Number of measurements
    sum: float         # Sum of measurements
    max: float         # Maximum value
    min: float         # Minimum value
    average: float     # Average value
    sumOfSquares: float # Sum of squared values
    msdev: float       # Mean square deviation
    stddev: float      # Standard deviation
```

## WebSocket Client Options

```python
class WebsocketOptions(TypedDict):
    domain: str        # API domain
    region: Optional[str]  # API region
    requestTimeout: float  # Request timeout
    connectTimeout: float  # Connection timeout
    packetOrderingTimeout: float  # Packet ordering timeout
    heartbeatInterval: float      # Heartbeat interval
    reconnectInterval: float      # Reconnect interval
    additionaRetryInterval: float # Additional retry interval
    retryTimeoutInSeconds: float  # Retry timeout
    minRetryDelayInSeconds: float # Min retry delay
    maxRetryDelayInSeconds: float # Max retry delay
```

# MetaAPI Cloud SDK API Documentation

## 初始化和连接管理

```python
from metaapi_cloud_sdk import MetaApi
from datetime import datetime
import asyncio

# 创建MetaAPI实例
api = MetaApi(token='your-token')

# 获取账户
account = await api.metatrader_account_api.get_account(account_id='your-account-id')

# 创建streaming连接
connection = await account.get_streaming_connection()

# 连接和同步
await connection.connect()
await connection.wait_synchronized()

# 连接选项
class SynchronizationOptions:
    instanceIndex: Optional[int]      # 账户实例索引，默认等待第一个实例同步
    applicationPattern: Optional[str]  # 应用正则表达式模式，默认是.*
    synchronizationId: Optional[str]  # 同步ID，默认使用最后的同步请求ID
    timeoutInSeconds: Optional[float] # 等待超时时间，默认5分钟
    intervalInMilliseconds: Optional[float] # 账户重载间隔，默认1秒
```

## 市场数据API

### 1. K线数据

```python
# 订阅K线数据
await connection.subscribe_to_market_data('EURUSD', {
    'type': 'candles',
    'timeframe': '1m'  # 支持的时间周期见下方
})

# MT5支持的时间周期：
# 1m, 2m, 3m, 4m, 5m, 6m, 10m, 12m, 15m, 20m, 30m
# 1h, 2h, 3h, 4h, 6h, 8h, 12h
# 1d, 1w, 1mn

# MT4支持的时间周期：
# 1m, 5m, 15m, 30m
# 1h, 4h
# 1d, 1w, 1mn

# K线数据回调处理
@connection.on_candle_data_received
async def process_candle(candle_data):
    """
    candle_data结构：
    {
        'symbol': 'EURUSD',          # 交易对
        'timeframe': '1m',           # 时间周期
        'time': '2023-01-01T00:00:00.000Z',  # K线时间
        'brokerTime': '2023-01-01 00:00:00', # 券商时间
        'open': 1.1000,              # 开盘价
        'high': 1.1100,              # 最高价
        'low': 1.0900,               # 最低价
        'close': 1.1050,             # 收盘价
        'tickVolume': 1000,          # tick成交量
        'spread': 1,                 # 点差
        'volume': 100                # 成交量
    }
    """
    print(f"收到K线数据: {candle_data}")

# 获取历史K线数据
candles = await connection.get_historical_candles('EURUSD', {
    'timeframe': '1h',
    'start': datetime(2023, 1, 1),
    'limit': 1000  # 最大1000条
})
```

### 2. Tick数据

```python
# 订阅Tick数据
await connection.subscribe_to_market_data('EURUSD', {
    'type': 'ticks'
})

# Tick数据回调处理
@connection.on_tick_data_received
async def process_tick(tick_data):
    """
    tick_data结构：
    {
        'symbol': 'EURUSD',          # 交易对
        'time': '2023-01-01T00:00:00.000Z',  # 时间
        'brokerTime': '2023-01-01 00:00:00', # 券商时间
        'bid': 1.1000,               # 买价
        'ask': 1.1001,               # 卖价
        'last': 1.1000,              # 最新成交价
        'volume': 1.0,               # 成交量
        'side': 'buy'                # 成交方向
    }
    """
    print(f"收到Tick数据: {tick_data}")

# 获取历史Tick数据
ticks = await connection.get_historical_ticks('EURUSD', {
    'start': datetime(2023, 1, 1),
    'offset': 0,
    'limit': 1000  # 最大1000条
})
```

### 3. 订单簿数据

```python
# 订阅订单簿数据
await connection.subscribe_to_market_data('EURUSD', {
    'type': 'books'
})

# 订单簿数据回调处理
@connection.on_book_data_received
async def process_book(book_data):
    """
    book_data结构：
    {
        'symbol': 'EURUSD',          # 交易对
        'time': '2023-01-01T00:00:00.000Z',  # 时间
        'brokerTime': '2023-01-01 00:00:00', # 券商时间
        'bids': [                    # 买单列表
            {'price': 1.1000, 'volume': 1.0},
            {'price': 1.0999, 'volume': 2.0}
        ],
        'asks': [                    # 卖单列表
            {'price': 1.1001, 'volume': 1.0},
            {'price': 1.1002, 'volume': 2.0}
        ]
    }
    """
    print(f"收到订单簿数据: {book_data}")
```

### 4. 市场信息查询

```python
# 获取交易品种规格
specification = await connection.get_symbol_specification('EURUSD')

# 获取交易品种价格
price = await connection.get_symbol_price('EURUSD')

# 获取所有可交易的交易品种
symbols = await connection.get_symbols()
```

### 5. 订阅管理

```python
# 取消单个品种订阅
await connection.unsubscribe_from_market_data('EURUSD')

# 取消所有订阅
await connection.unsubscribe_from_all_market_data()

# 刷新订阅（在连接中断后重新订阅）
await connection.refresh_market_data_subscriptions()
```

## 完整的流数据处理示例

```python
async def handle_streaming_data():
    try:
        # 1. 初始化连接
        connection = await account.get_streaming_connection()
        await connection.connect()
        await connection.wait_synchronized()
        
        # 2. 设置数据处理回调
        @connection.on_connected
        async def on_connected():
            print("连接已建立")
            
        @connection.on_disconnected
        async def on_disconnected():
            print("连接已断开")
            
        @connection.on_error
        async def on_error(error):
            print(f"发生错误: {error}")
            
        @connection.on_candle_data_received
        async def on_candle(candle):
            print(f"K线数据: {candle}")
            
        @connection.on_tick_data_received
        async def on_tick(tick):
            print(f"Tick数据: {tick}")
            
        @connection.on_book_data_received
        async def on_book(book):
            print(f"订单簿数据: {book}")
        
        # 3. 订阅数据
        symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
        for symbol in symbols:
            await connection.subscribe_to_market_data(symbol, {
                'type': ['ticks', 'candles', 'books'],
                'timeframes': ['1m', '5m']
            })
        
        # 4. 保持连接活跃
        while True:
            if not await connection.is_connected():
                await connection.connect()
                await connection.wait_synchronized()
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"错误: {e}")
    finally:
        await connection.close()

# 运行流数据处理
asyncio.run(handle_streaming_data())
```

## 错误处理和连接管理

```python
# 重试选项
class StreamingRetryOptions:
    retries: int = 5                  # 最大重试次数
    minDelayInSeconds: float = 1      # 最小重试延迟
    maxDelayInSeconds: float = 30     # 最大重试延迟
    subscriptionRetryIntervalInSeconds: float = 60  # 订阅重试间隔

# 连接状态管理
async def maintain_connection():
    while True:
        try:
            if not connection.is_connected():
                print("连接断开，尝试重连...")
                await connection.connect()
                await connection.wait_synchronized()
                await connection.refresh_market_data_subscriptions()
                
        except Exception as e:
            print(f"连接错误: {e}")
            await asyncio.sleep(5)
            continue
            
        await asyncio.sleep(1)

# 连接状态检查
is_connected = await connection.is_connected()
is_synchronized = await connection.is_synchronized()

# 获取连接健康状态
health_status = await connection.get_health_status()

# 等待特定状态
await connection.wait_synchronized(timeout=300)  # 等待同步，超时5分钟
await connection.wait_connected(timeout=60)      # 等待连接，超时1分钟

# 获取服务器时间
server_time = await connection.get_server_time()

# 获取账户信息
account_information = await connection.get_account_information()

# 资源清理
async def cleanup():
    try:
        # 取消所有订阅
        await connection.unsubscribe_from_all_market_data()
        # 关闭连接
        await connection.close()
    except Exception as e:
        print(f"清理时发生错误: {e}")