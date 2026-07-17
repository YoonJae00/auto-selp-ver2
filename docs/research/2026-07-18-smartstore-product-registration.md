# 네이버 스마트스토어 상품 등록 조사 및 현재 시스템 간극 분석

Date: 2026-07-18
Status: Research complete, implementation not started
Target API documentation: Naver Commerce API 2.82.0 (2026-07-07)
Context7 library: `/websites/apicenter_commerce_naver` (High reputation)

## 1. 이 문서의 목적

이 문서는 다음 세션에서 네이버 스마트스토어 실제 상품 등록 기능을 바로 설계하고 구현할 수 있도록 아래 내용을 한곳에 보존한다.

1. 네이버 커머스 API의 상품 등록 순서
2. `POST /v2/products` 요청 구조와 필수/조건부 필드
3. 현재 상품관리 데이터에서 이미 제공되는 값
4. 현재 Smartstore adapter가 만드는 payload와 네이버 스키마의 차이
5. 새 컬럼이 필요한 값과 기존 JSON/설정으로 처리할 값의 구분
6. 실제 제출 worker를 구현할 때의 권장 순서와 테스트 범위

이 문서는 구현 계획서가 아니라 구현 전 조사 기준선이다. 네이버 API는 카테고리와 계정 권한에 따라 조건이 달라지므로 실제 구현 시작 시 대상 카테고리와 테스트 판매자 계정으로 메타데이터 API를 다시 호출해야 한다.

## 2. 최종 결론

현재 상품관리에서 가공한 상품은 스마트스토어에 그대로 등록할 수 없다.

현재 확보된 값:

- 상품명
- 스마트스토어 리프 카테고리 ID
- 도매가와 가격 정책으로 계산한 판매가
- 대표/추가 이미지 원본 URL
- 상세 HTML 또는 상세 이미지 콘텐츠
- 원산지 원문
- 옵션 일부
- 카테고리 속성 매핑 결과 일부

현재 부족하거나 잘못된 값:

- `originProduct.statusType`
- 네이버 이미지 업로드 API가 반환한 이미지 URL
- 코드화된 `originAreaInfo`
- 등록 시 필수인 `productInfoProvidedNotice`
- 스마트스토어 채널 필수 플래그
- 일반 실물상품에 필요한 배송/반품/교환 설정
- 상품 기본 재고 또는 신뢰할 수 있는 옵션 재고
- 카테고리별 인증/면제/단위가격/도서 등 조건부 정보
- 네이버 스키마에 맞는 옵션 그룹 구조
- 실제 외부 API 제출 worker

현재 `/submissions`는 submission job과 attempt를 DB에 기록하고 draft 상태를 `submitting`으로 변경할 뿐 네이버 API를 호출하지 않는다. 따라서 payload 보완만으로도 등록은 완료되지 않는다.

## 3. 다음 세션 빠른 시작

다음 세션은 아래 순서로 시작하는 것이 가장 안전하다.

1. 이 문서의 `10. 현재 코드의 차단 결함`을 먼저 수정한다.
2. Smartstore 전용 account settings 스키마를 정의한다.
3. 일반 배송 실물상품 한 카테고리를 기준으로 최소 유효 payload fixture를 만든다.
4. 이미지 업로드와 `POST /v2/products`를 담당하는 marketplace-side client를 만든다.
5. submission worker가 queued attempt를 가져와 실제 API를 호출하도록 연결한다.
6. 네이버 sandbox가 없으면 승인된 테스트 상품/계정으로 최소 1건을 등록하고 바로 판매 중지 또는 삭제하는 운영 절차를 준비한다.

첫 구현 범위는 다음으로 제한하는 것이 좋다.

- `type=SELF` 판매자 계정
- 일반 배송 `NORMAL`
- 단일 원상품 등록 `POST /v2/products`
- 일반 실물상품
- 조합형 옵션 0~3단계
- N배송, 렌탈, E쿠폰, 도서, 지금배달, 그룹상품은 후속 범위

## 4. 조사 근거와 문서 해석 원칙

### 4.1 Context7

AGENTS 지침에 따라 Context7를 먼저 사용했다.

- Resolve 결과: `/websites/apicenter_commerce_naver`
- 이름: Naver Commerce API
- Source reputation: High
- 확인 주제:
  - 상품 등록 `POST /v2/products`
  - 원상품/스마트스토어 채널상품 구조체
  - OAuth 토큰
  - 상품 이미지 업로드
  - 배송, 원산지, 옵션, 고시, 인증 조건

Context7 검색 결과는 일부 복합 스키마를 생략하거나 솔루션 사업자용 `SELLER` 인증 문서를 함께 반환했다. 따라서 최종 판정은 아래 네이버 공식 current 문서를 직접 대조했다.

### 4.2 공식 문서 기준

- [커머스 API current](https://apicenter.commerce.naver.com/docs/commerce-api/current)
- [(v2) 상품 등록](https://apicenter.commerce.naver.com/docs/commerce-api/current/create-product-product)
- [원상품 정보 구조체](https://apicenter.commerce.naver.com/docs/commerce-api/current/schemas/%EC%9B%90%EC%83%81%ED%92%88-%EC%A0%95%EB%B3%B4-%EA%B5%AC%EC%A1%B0%EC%B2%B4)
- [스마트스토어 채널상품 정보 구조체](https://apicenter.commerce.naver.com/docs/commerce-api/current/schemas/%EC%8A%A4%EB%A7%88%ED%8A%B8%EC%8A%A4%ED%86%A0%EC%96%B4-%EC%B1%84%EB%84%90%EC%83%81%ED%92%88-%EC%A0%95%EB%B3%B4-%EA%B5%AC%EC%A1%B0%EC%B2%B4)
- [OAuth 2.0](https://apicenter.commerce.naver.com/docs/commerce-api/current/o-auth-2-0)
- [인증 토큰 발급 요청](https://apicenter.commerce.naver.com/docs/commerce-api/current/exchange-sellers-auth)
- [상품 이미지 다건 등록](https://apicenter.commerce.naver.com/docs/commerce-api/current/upload-product)
- [전체 카테고리 조회](https://apicenter.commerce.naver.com/docs/commerce-api/current/get-category-list-product)
- [카테고리별 속성 조회](https://apicenter.commerce.naver.com/docs/commerce-api/current/get-attribute-list-product)
- [원산지 코드 정보 전체 조회](https://apicenter.commerce.naver.com/docs/commerce-api/current/get-all-origin-area-list-product)
- [상품정보제공고시 상품군 목록 조회](https://apicenter.commerce.naver.com/docs/commerce-api/current/get-all-product-info-provided-notice-type-vo-product)
- [카테고리별 표준형 옵션 조회](https://apicenter.commerce.naver.com/docs/commerce-api/current/get-standard-option-by-category-product)

### 4.3 필수성 표기 원칙

이 문서에서는 필드를 다음과 같이 구분한다.

- **필수**: 공식 구조체에 `required`로 표시되거나 등록 시 필수라고 명시됨
- **조건부 필수**: 카테고리, 배송 방법, 인증 유형, 상품 유형 또는 다른 필드값에 따라 필수
- **운영상 필수**: API 스키마상 생략 가능하지만 현재 서비스가 취급하는 일반 실물상품을 정상 판매하려면 사실상 필요
- **선택**: 생략 가능하며 기본값 또는 기능 미사용 상태가 명확함

`required`가 중첩 객체 안에 표시된 경우 부모 객체를 사용할 때만 필수일 수 있다. 예를 들어 `deliveryInfo`는 일반 상품에서 생략할 수 있지만, 입력하면 그 안의 `deliveryType`, `deliveryAttributeType`, `deliveryFee`, `claimDeliveryInfo` 규칙을 만족해야 한다.

## 5. 네이버 상품 등록 전체 흐름

### 5.1 Base URL

```text
https://api.commerce.naver.com/external
```

### 5.2 인증 토큰 발급

현재 repo의 네이버 클라이언트는 판매자 본인 애플리케이션용 `SELF` 타입을 사용한다.

```http
POST /v1/oauth2/token
Content-Type: application/x-www-form-urlencoded
```

핵심 파라미터:

| 필드 | 의미 |
| --- | --- |
| `client_id` | 커머스 API 애플리케이션 ID |
| `timestamp` | 밀리초 Unix timestamp |
| `client_secret_sign` | bcrypt 기반 서명 후 Base64 인코딩 |
| `grant_type` | `client_credentials` |
| `type` | 현재 repo 흐름은 `SELF` |

현재 코드의 서명식:

```text
base64(bcrypt("{client_id}_{timestamp_ms}", client_secret_as_salt))
```

토큰은 공식 문서상 3시간(10,800초) 유효하다. 같은 리소스의 기존 토큰이 30분 이상 남으면 기존 토큰이 반환될 수 있다.

주의:

- Context7가 함께 반환한 솔루션 제공자용 `SELLER` 흐름에는 `account_id`가 추가된다.
- 현재 시스템이 사용자별 Smartstore 계정을 지원하려면 `type=SELF` 전역 환경변수 하나를 공유할지, 계정별 credential을 사용할지 먼저 결정해야 한다.
- 현재 `NaverCommerceClient`는 processor 전역 환경변수를 읽으며 marketplace의 암호화된 계정 credential을 사용하지 않는다.

### 5.3 등록 메타데이터 조회

상품 등록 전에 아래 데이터를 조회하고 캐시해야 한다.

| 목적 | API | 비고 |
| --- | --- | --- |
| 리프 카테고리 확인 | `GET /v1/categories` | 카테고리 변경 가능성 때문에 주기적 갱신 필요 |
| 카테고리 속성 정의 | `GET /v1/product-attributes/attributes?categoryId=...` | 필수 속성과 분류형 확인 |
| 카테고리 속성값 | `GET /v1/product-attributes/attribute-values?categoryId=...` | `attributeValueSeq` 선택에 필요 |
| 원산지 코드 | `GET /v1/product-origin-areas` | 원산지 원문을 코드로 정규화할 때 필요 |
| 상품정보제공고시 상품군 | `GET /v1/products-for-provided-notice` | 대카테고리 입력 시 추천 상품군 반환 |
| 표준형 옵션 | `GET /v1/options/standard-options` | 표준형 옵션을 쓸 때만 필요 |

그룹상품은 별도 `POST /v2/standard-group-products` 흐름이며, 판매 옵션 가이드는 `GET /v2/standard-purchase-option-guides`를 사용한다. 현재 단일 원상품 등록 범위와 혼합하지 않는다.

### 5.4 이미지 업로드

```http
POST /v1/product-images/upload
Content-Type: multipart/form-data
Authorization: Bearer {access_token}
```

규칙:

- `imageFiles` 필수
- 한 번에 최대 10개
- JPG, GIF, PNG, BMP 지원
- 대표 이미지는 1000x1000 권장
- 원상품에는 대표 이미지 1개와 추가 이미지 최대 9개
- 최종 상품 payload에는 이 API 응답의 `images[].url`을 사용해야 함

현재 adapter는 공급사 URL을 그대로 `representativeImage.url`에 넣으므로 제출 전 업로드 단계가 반드시 필요하다.

### 5.5 최종 등록

```http
POST /v2/products
Authorization: Bearer {access_token}
Content-Type: application/json
Accept: application/json;charset=UTF-8
```

최상위 구조:

```json
{
  "originProduct": {},
  "smartstoreChannelProduct": {}
}
```

`BAD_REQUEST` 응답에서 `invalidInputs`만으로 원인을 판단하기 어려울 수 있으므로 `message`도 함께 저장해야 한다.

## 6. `originProduct` 상세 구조

### 6.1 핵심 필드

| 필드 | 타입 | 필수성 | 제약/설명 |
| --- | --- | --- | --- |
| `statusType` | string | 필수 | 등록 시 `SALE`만 사용. `stockQuantity=0`이면 품절 처리 가능 |
| `saleType` | string | 선택 | `NEW`, `OLD`; 신규 일반상품은 `NEW` 기본 권장 |
| `leafCategoryId` | string | 등록 핵심 | 최종 리프 카테고리 ID |
| `name` | string | 필수 | 원상품명 |
| `detailContent` | string | 필수 | 상품 상세 HTML/콘텐츠 |
| `images` | object | 필수 | 대표 이미지 필수, 추가 이미지 최대 9개 |
| `saleStartDate` | date-time | 선택 | 지정 시 공식 형식 사용 |
| `saleEndDate` | date-time | 선택 | 지정 시 공식 형식 사용 |
| `salePrice` | int64 | 필수 | 최대 999,999,990 |
| `stockQuantity` | int32 | 선택/운영상 중요 | 최대 99,999,999 |
| `deliveryInfo` | object | 조건부/운영상 중요 | 생략 시 배송 없는 상품 |
| `detailAttribute` | object | 필수 | 고시, 원산지, 옵션, 속성, 인증 등 |
| `customerBenefit` | object | 선택 | 할인/포인트/리뷰 혜택 |

### 6.2 이미지 구조

```json
{
  "images": {
    "representativeImage": {
      "url": "https://shop-phinf.pstatic.net/..."
    },
    "optionalImages": [
      { "url": "https://shop-phinf.pstatic.net/..." }
    ]
  }
}
```

`optionalImages`는 없으면 빈 배열보다 필드 생략을 우선 고려한다. 실제 네이버 스키마가 허용하더라도 불필요한 빈 중첩 객체는 보내지 않는 편이 오류 가능성을 줄인다.

## 7. 배송과 클레임

### 7.1 `deliveryInfo`

`deliveryInfo`를 생략하면 배송 없는 상품으로 등록된다. 현재 시스템은 도매 실물상품을 다루므로 일반 등록 경로에서는 운영상 필수로 취급한다.

| 필드 | 필수성 | 설명 |
| --- | --- | --- |
| `deliveryType` | `deliveryInfo` 사용 시 필수 | `DELIVERY` 또는 `DIRECT` |
| `deliveryAttributeType` | 필수 | 일반 상품 기본은 `NORMAL` |
| `deliveryCompany` | `DELIVERY`일 때 필수 | 네이버 택배사 코드 |
| `outboundLocationId` | N판매자배송 계열 조건부 | 판매자 창고 ID |
| `deliveryBundleGroupUsable` | 선택 | 묶음배송 여부 |
| `deliveryBundleGroupId` | 조건부 | 묶음배송 그룹 코드 |
| `deliveryFee` | 필수 | 배송비 구조 |
| `claimDeliveryInfo` | 필수 | 반품/교환 구조 |
| `installation` | N희망일배송 조건부 | 설치 여부 |
| `installationFee` | 설치 상품 조건부 | 별도 설치비 여부 |
| `productLogistics` | 풀필먼트 조건부 | 물류사 정보 |

지원 배송 속성에는 `NORMAL`, `TODAY`, `OPTION_TODAY`, `HOPE`, `TODAY_ARRIVAL`, `DAWN_ARRIVAL`, `ARRIVAL_GUARANTEE`, `SELLER_GUARANTEE`, `HOPE_SELLER_GUARANTEE`, `QUICK`, `PICKUP`, `QUICK_PICKUP` 등이 있다. 첫 구현은 `NORMAL`만 지원한다.

### 7.2 `deliveryFee`

| 필드 | 필수성 | 설명 |
| --- | --- | --- |
| `deliveryFeeType` | 선택, 기본 `FREE` | `FREE`, `CONDITIONAL_FREE`, `PAID`, `UNIT_QUANTITY_PAID`, `RANGE_QUANTITY_PAID` |
| `baseFee` | 유료 계열 조건부 | 기본 배송비, 최대 100,000 |
| `freeConditionalAmount` | `CONDITIONAL_FREE` 조건부 | 무료 조건 금액 |
| `repeatQuantity` | 수량별 반복 조건부 | 반복 부과 수량 |
| `secondBaseQuantity` | 구간별 조건부 | 2구간 수량 |
| `secondExtraFee` | 구간별 조건부 | 2구간 추가비 |
| `thirdBaseQuantity` | 구간별 조건부 | 3구간 수량 |
| `thirdExtraFee` | 구간별 조건부 | 3구간 추가비 |
| `deliveryFeePayType` | 정책에 따라 입력 | `COLLECT`, `PREPAID`, `COLLECT_OR_PREPAID` |
| `deliveryFeeByArea` | 지역 추가비 사용 시 | 2권역/3권역 설정 |

### 7.3 `claimDeliveryInfo`

| 필드 | 필수성 | 설명 |
| --- | --- | --- |
| `returnDeliveryCompanyPriorityType` | 선택 | 미입력 시 `PRIMARY` |
| `returnDeliveryFee` | 필수 | 최대 1,000,000 |
| `exchangeDeliveryFee` | 필수 | 최대 1,000,000 |
| `shippingAddressId` | 일반 배송에서 필요 | 출고지 주소록 번호 |
| `returnAddressId` | 일반 배송에서 필요 | 반품/교환지 주소록 번호 |
| `freeReturnInsuranceYn` | 선택 | 반품안심케어 |

배송/반품 값은 상품마다 반복 입력하지 않고 Smartstore account settings에 두는 것이 기존 아키텍처와 맞다.

## 8. `detailAttribute` 상세 구조

### 8.1 네이버 쇼핑 검색 정보

`naverShoppingSearchInfo`에는 아래 값이 들어갈 수 있다.

- `modelId`
- `modelName`
- `manufacturerName`
- `brandId`
- `brandName`
- 카탈로그 매칭 관련 응답 필드
- `manufactureDefineNo`

현재 `brand_name`은 Product에 있지만 프로덕션 가공 코드에서 값을 설정하는 경로가 없어 대부분 `None`일 가능성이 높다. 제조사와 모델명은 Product 모델에 없다.

### 8.2 A/S 정보

`afterServiceInfo`를 입력하면 다음 두 필드가 필수다.

```json
{
  "afterServiceInfo": {
    "afterServiceTelephoneNumber": "...",
    "afterServiceGuideContent": "..."
  }
}
```

A/S 기본값은 account settings에 두고, 특정 상품만 `override_patch`로 덮어쓰는 방향이 적절하다.

### 8.3 구매 수량 제한

선택 필드:

- `minPurchaseQuantity`: 최대 10,000
- `maxPurchaseQuantityPerId`: 최대 99,999,999
- `maxPurchaseQuantityPerOrder`: 최대 10,000

### 8.4 원산지

정확한 구조:

```json
{
  "originAreaInfo": {
    "originAreaCode": "02",
    "importer": "수입사명",
    "content": null,
    "plural": false
  }
}
```

코드:

| 코드 | 의미 | 추가 필드 |
| --- | --- | --- |
| `00` | 국산 | 세부 원산지 API 결과에 따라 상세 코드 사용 가능 |
| `01` | 원양산 | 상품에 맞게 선택 |
| `02` | 수입산 | `importer` 필수 |
| `03` | 기타-상세 설명에 표시 | 상세설명과 일치시켜야 함 |
| `04` | 기타-직접 입력 | `content` 필수 |
| `05` | 원산지 표기 의무 대상 아님 | 실제 법적 대상 여부 확인 필요 |

현재 `origin="해외|아시아|중국"` 같은 원문만으로는 `originAreaCode`와 수입사명을 만들 수 없다. 코드 매핑 테이블과 운영자 검토가 필요하다.

### 8.5 판매자 코드

```json
{
  "sellerCodeInfo": {
    "sellerManagementCode": "ABC-001",
    "sellerBarcode": null,
    "sellerCustomCode1": null,
    "sellerCustomCode2": null
  }
}
```

`Product.product_code`를 `sellerManagementCode`로 재사용할 수 있다. 현재 테스트의 `listing_defaults.sellerManagementCode`처럼 `smartstoreChannelProduct`에 넣으면 위치가 틀리다.

### 8.6 옵션

옵션이 없으면 `optionInfo` 자체를 생략하는 것을 기본으로 한다.

조합형 옵션의 올바른 모양:

```json
{
  "optionInfo": {
    "optionCombinationGroupNames": {
      "optionGroupName1": "색상",
      "optionGroupName2": "사이즈"
    },
    "optionCombinations": [
      {
        "optionName1": "블랙",
        "optionName2": "L",
        "stockQuantity": 12,
        "price": 0,
        "usable": true,
        "sellerManagerCode": "P-100-1"
      }
    ],
    "useStockManagement": true
  }
}
```

규칙:

- 단독형과 조합형은 함께 사용할 수 없음
- 일반 조합형은 최대 3개 옵션 그룹
- 지점형 특수 옵션은 4개 가능하지만 첫 구현 범위에서 제외
- `optionName1`은 조합형 행에서 필수
- `stockQuantity` 미입력 시 0으로 설정될 수 있음
- `price`는 기준 판매가 대비 옵션가
- `sellerManagerCode`는 옵션 SKU로 매핑 가능
- 재고 관리 사용 여부가 없거나 false면 문서상 수량이 9,999로 설정되는 동작이 있으므로 명시적으로 정책 결정 필요

현재 `SmartstoreAdapter`는 `optionCombinationGroupNames`를 객체가 아니라 문자열 배열로 만든다. legacy `option_variants`는 네이버 변환 없이 그대로 `optionCombinations`에 복사한다.

### 8.7 세금과 인증

세금:

- `taxType`: `TAX`, `DUTYFREE`, `SMALL`
- `customsTaxType`: `NOT_APPLICABLE`, `INCLUDED`, `EXCLUDED`

인증 목록 `productCertificationInfos[]`:

| 필드 | 필수성 |
| --- | --- |
| `certificationInfoId` | 필수 |
| `certificationKindType` | 선택, 미입력 시 `ETC` |
| `name` | 일반적으로 필수, 일부 공급자적합성 유형 예외 |
| `certificationNumber` | 일반적으로 필수, 일부 공급자적합성 유형 예외 |
| `certificationMark` | 선택, 기본 false |
| `companyName` | 특정 전파/어린이제품 인증에서 필수 |
| `certificationDate` | 해당 시 입력 |

인증 종류:

- `KC_CERTIFICATION`
- `CHILD_CERTIFICATION`
- `GREEN_PRODUCTS`
- `OVERSEAS`
- `PARALLEL_IMPORT`
- `ETC`

인증 제외 정보 `certificationTargetExcludeContent`:

- `childCertifiedProductExclusionYn`: 어린이제품 대상 카테고리에서 필수
- `kcCertifiedProductExclusionYn`: KC 대상 카테고리에서 필수
  - `TRUE`
  - `FALSE`
  - `KC_EXEMPTION_OBJECT`
- `kcExemptionType`: 안전기준준수/구매대행/병행수입에서 필수
  - `SAFE_CRITERION`
  - `OVERSEAS`
  - `PARALLEL_IMPORT`
- `greenCertifiedProductExclusionYn`: 친환경 대상 카테고리에서 필수

인증 대상 여부는 상품명이나 카테고리명만 보고 임의 추론하면 안 된다. 카테고리 메타데이터와 판매자 입력을 조합해야 한다.

### 8.8 미성년자 구매, E쿠폰, 도서

- `minorPurchasable`: 미성년자 구매 가능 여부
- E쿠폰은 `periodType`, 유효기간, 발행처, 연락처, 사용 장소 등의 별도 필드가 필요
- 도서 카테고리는 `isbn13`, `issn`, `bookInfo.publishDay`, `publisher`, `authors` 등 별도 필드가 필요
- 일반 상품 첫 구현에서는 E쿠폰/도서 카테고리를 명시적으로 차단하는 것이 안전함

### 8.9 상품정보제공고시

`productInfoProvidedNotice`는 상품 등록 시 필수다.

```json
{
  "productInfoProvidedNotice": {
    "productInfoProvidedNoticeType": "KITCHEN_UTENSILS",
    "kitchenUtensils": {
      "...": "카테고리별 필드"
    }
  }
}
```

지원 타입에는 다음이 포함된다.

```text
WEAR, SHOES, BAG, FASHION_ITEMS, SLEEPING_GEAR, FURNITURE,
IMAGE_APPLIANCES, HOME_APPLIANCES, SEASON_APPLIANCES,
OFFICE_APPLIANCES, OPTICS_APPLIANCES, MICROELECTRONICS,
CELLPHONE, NAVIGATION, CAR_ARTICLES, MEDICAL_APPLIANCES,
KITCHEN_UTENSILS, COSMETIC, JEWELLERY, FOOD, GENERAL_FOOD,
DIET_FOOD, KIDS, MUSICAL_INSTRUMENT, SPORTS_EQUIPMENT, BOOKS,
LODGMENT_RESERVATION, TRAVEL_PACKAGE, AIRLINE_TICKET, RENT_CAR,
RENTAL_HA, RENTAL_ETC, DIGITAL_CONTENTS, GIFT_CARD, MOBILE_COUPON,
MOVIE_SHOW, ETC_SERVICE, BIOCHEMISTRY, BIOCIDAL, ETC
```

각 타입은 서로 다른 중첩 객체와 필수 필드를 가진다. 모든 타입을 하나의 정규화된 DB 테이블로 펴지 않는다.

일반 `ETC` 예시에서도 품명, 모델명, 제조자, 청약철회/품질보증/보상 관련 필드 등이 필요하다. 일부 법정 문구는 문서 기본값 또는 상품상세 참조 코드를 사용할 수 있지만, 해당 타입 문서를 조회해 허용되는 값만 보내야 한다.

### 8.10 상품 속성

정확한 필드명은 `productAttributes`다.

```json
{
  "productAttributes": [
    {
      "attributeSeq": 123,
      "attributeValueSeq": 456
    },
    {
      "attributeSeq": 789,
      "attributeRealValue": "500",
      "attributeRealValueUnitCode": "ML"
    }
  ]
}
```

선택형은 `attributeValueSeq`, 범위/직접값은 `attributeRealValue`와 단위 코드를 사용한다. 현재 mapper는 이 기본 형태를 만들 수 있지만 저장 shape와 adapter 기대 shape가 다르다.

### 8.11 SEO, 태그, 단위가격

선택 SEO 필드:

- `seoInfo.pageTitle`: 최대 100자
- `seoInfo.metaDescription`: 최대 160자
- `seoInfo.sellerTags[]`: `text` 필수, 추천 태그면 `code`와 이름 일치 필요

단위가격 표시 의무 카테고리에서는 `unitCapacity`가 필수다.

```json
{
  "unitCapacity": {
    "unitPriceYn": true,
    "totalCapacityValue": 1000,
    "unitCapacity": 100,
    "indicationUnit": "ml"
  }
}
```

`unitPriceYn=true`이면 나머지 세 값이 모두 필수다. 지원 단위의 대소문자도 문서 기준과 일치시켜야 한다.

## 9. `smartstoreChannelProduct`

| 필드 | 필수성 | 설명 |
| --- | --- | --- |
| `channelProductName` | 선택 | 미입력 시 원상품명 적용 |
| `bbsSeq` | 선택 | 공지사항/콘텐츠 게시글 일련번호 |
| `storeKeepExclusiveProduct` | 선택 | 미입력 시 false |
| `naverShoppingRegistration` | 필수 | 네이버쇼핑 등록 여부. 광고주가 아니면 false 저장 가능 |
| `channelProductDisplayStatusType` | 필수 | 등록/수정 입력은 `ON` 또는 `SUSPENSION` |

일반 등록 기본값 예시:

```json
{
  "smartstoreChannelProduct": {
    "naverShoppingRegistration": false,
    "channelProductDisplayStatusType": "ON"
  }
}
```

이 두 값은 상품별 컬럼보다 account-level listing defaults가 적합하다. 필요하면 개별 draft override로 수정한다.

## 10. 현재 repo 데이터 흐름

### 10.1 Product 모델

주요 파일: [`services/processor/models.py`](../../services/processor/models.py)

현재 Product의 관련 필드:

| Product 필드 | snapshot 필드 | Smartstore 사용 |
| --- | --- | --- |
| `product_code` | `product_code` | 현재 미사용, seller management code로 재사용 가능 |
| `wholesale_product_id` | `wholesale_product_id` | 현재 미사용 |
| `price_wholesale` | `price.wholesale` | 가격 정책 계산 원가 |
| `price_retail` | `price.retail` | adapter 미사용 |
| `price_min_selling` | `price.minimum_selling` | adapter 미사용 |
| `origin` | `origin` | 잘못된 `rawOrigin`으로 사용 |
| `option_variants` | `options` | 변환 없이 네이버 옵션에 복사 |
| `standard_options` | `standard_options` | 조합형 옵션으로 일부 변환 |
| `images_list` | `images.list` | 원본 URL을 네이버 URL처럼 사용 |
| `image_detail` | `images.detail_content` | `detailContent` |
| `original_name` | `original_name` | 제목 fallback 재료 |
| `refined_name` | `refined_name` | 제목 재료 |
| `brand_name` | `brand_name` | 제목 재료이나 실제 저장 경로 미비 |
| `keywords` | `keywords` | 첫 키워드 제목 재료 |

Product에 없는 일반 상품 재료:

- 상품 기본 재고
- 제조사
- 모델명
- 수입사
- 코드화된 원산지

### 10.2 ProductPlatformMapping

현재 보유:

- `category_id`
- `category_path`
- `product_name`
- `mapped_attributes`
- sync 상태와 remote platform product ID

현재 `mapped_attributes` SQLAlchemy 타입 힌트는 dict지만 네이버 가공 결과는 실제로 list를 저장한다.

### 10.3 Marketplace snapshot

주요 파일: [`services/processor/main.py`](../../services/processor/main.py)

현재 snapshot은 다음을 노출한다.

```text
product_id, version, product_code, wholesale_product_id,
original_name, refined_name, brand_name, keywords, origin,
price.{wholesale,retail,minimum_selling},
images.{list,detail_content},
options, standard_options,
market_categories.{category_id,category_path,product_name,mapped_attributes}
```

미노출:

- `wholesale_status`
- 상품 기본 재고
- 제조사/모델명/수입사
- Smartstore 고시/인증/배송 override 재료

### 10.4 Draft 생성

주요 파일: [`services/marketplace/adapters/smartstore.py`](../../services/marketplace/adapters/smartstore.py)

현재 생성 payload:

```json
{
  "originProduct": {
    "name": "...",
    "leafCategoryId": "...",
    "salePrice": 17200,
    "images": {
      "representativeImage": { "url": "공급사 URL" },
      "optionalImages": []
    },
    "detailContent": "...",
    "detailAttribute": {
      "originAreaInfo": { "rawOrigin": "해외|아시아|중국" },
      "optionInfo": {}
    }
  },
  "smartstoreChannelProduct": {},
  "pricing": {}
}
```

현재 로컬 validation은 category, title, primary image, sale price, origin, detail content, pricing policy만 확인한다. 네이버 필수 필드 전체를 검증하지 않는다.

### 10.5 제출

주요 파일:

- [`services/marketplace/main.py`](../../services/marketplace/main.py)
- [`services/marketplace/tasks.py`](../../services/marketplace/tasks.py)
- [`services/processor/clients/naver_commerce_client.py`](../../services/processor/clients/naver_commerce_client.py)

현재 상태:

- `POST /submissions`가 job과 attempt를 생성함
- draft 상태를 `submitting`으로 변경함
- `submitted_payload`를 DB에 저장함
- submission Celery task가 없음
- Smartstore create/update API client 메서드가 없음
- response/error/remote_product_id를 갱신하는 코드가 없음
- 사용자 계정 credential을 해독해 API 요청에 사용하는 코드가 없음

## 11. 현재 코드의 차단 결함

### P0-1. `mapped_attributes` shape 불일치

실제 저장:

```python
naver_mapping.mapped_attributes = state["mapped_attributes"].get("naver_attributes")
```

`NaverAttributeMapper` 반환형은 `list[dict]`다.

Adapter 기대:

```python
mapped_attrs.get("naver_attributes")
```

실데이터가 비어 있지 않은 list면 `AttributeError: 'list' object has no attribute 'get'`가 발생한다. 테스트 fixture가 실제와 다른 nested dict를 사용해 결함을 숨긴다.

### P0-2. 원산지 스키마 오류

현재:

```json
{ "originAreaInfo": { "rawOrigin": "..." } }
```

네이버는 `originAreaCode`와 조건부 `importer`, `content`, `plural`을 요구한다. `rawOrigin`은 네이버 필드가 아니다.

### P0-3. 옵션 그룹 구조 오류

현재 `optionCombinationGroupNames`는 list다. 네이버는 아래 object를 요구한다.

```json
{
  "optionGroupName1": "색상",
  "optionGroupName2": "사이즈"
}
```

legacy option은 네이버 변환 없이 복사되므로 `name`, `price_wholesale`, `position` 같은 내부 필드가 그대로 전송 후보가 된다.

### P0-4. 필수 필드 누락

최소 누락:

- `originProduct.statusType`
- `detailAttribute.productInfoProvidedNotice`
- `smartstoreChannelProduct.naverShoppingRegistration`
- `smartstoreChannelProduct.channelProductDisplayStatusType`

### P0-5. 이미지 업로드 미구현

공급사 URL을 네이버 이미지 URL처럼 사용한다. 제출 worker가 이미지 다운로드/검증/업로드/응답 URL 치환을 수행해야 한다.

### P0-6. 내부 `pricing` 메타가 외부 payload에 섞임

`generated_payload` 최상위 `pricing`은 내부 수익 계산용이다. 제출 attempt가 이를 그대로 복사한다. 네이버 요청 body를 만들 때 제거하거나 draft metadata와 외부 request body를 분리해야 한다.

### P0-7. UI override 경로 불일치

UI는 다음 top-level patch를 만든다.

```json
{
  "title": "...",
  "salePrice": 10000,
  "categoryId": "...",
  "origin": "...",
  "detailContent": "...",
  "images": [],
  "options": []
}
```

실 payload는 `originProduct.name`, `originProduct.salePrice`처럼 중첩되어 있다. backend deep merge는 top-level 필드를 추가할 뿐 원본 필드를 덮어쓰지 못한다.

### P0-8. 실제 submission worker 없음

현재 Celery에는 draft generation task만 있다. queued submission attempt가 실행되지 않아 draft가 `submitting`에 고정된다.

### P1-1. credential 소유권 불일치

- marketplace account credential은 암호화 저장됨
- processor의 Naver client는 전역 환경변수를 사용함
- marketplace submission에서 credential을 해독해 쓰는 경로가 없음

실제 제출 client는 marketplace 서비스에 두고 `MarketAccount.credentials_encrypted`를 사용해야 한다.

### P1-2. 제출 직전 재검증 없음

현재 생성 당시 `validation_result`만 확인한다. override와 최신 account settings를 합친 effective payload를 제출 직전 다시 검증해야 한다.

## 12. 필드별 확보 여부와 조치

| 네이버 필드 | 필수성 | 현재 소스 | 현재 상태 | 조치 |
| --- | --- | --- | --- | --- |
| `statusType` | 필수 | 없음 | 누락 | adapter 기본 `SALE` |
| `saleType` | 선택 | 없음 | 누락 | adapter 기본 `NEW` |
| `leafCategoryId` | 등록 핵심 | mapping.category_id | nullable | 등록 전 리프 여부 검증 |
| `name` | 필수 | product_name/refined_name | 있음 | 길이/금칙어 검증 추가 |
| `detailContent` | 필수 | image_detail | nullable | 빈 값 차단 |
| 대표 이미지 | 필수 | images_list[0] | 원본 URL | 네이버 업로드 후 URL 치환 |
| 추가 이미지 | 선택 | images_list[1:] | 원본 URL | 최대 9개 업로드 |
| `salePrice` | 필수 | pricing policy | 조건부 있음 | 정책/최소판매가 검증 |
| `stockQuantity` | 운영상 필요 | 없음 | 누락 | generic Product 필드 후보 |
| `deliveryInfo` | 운영상 필요 | account settings 존재 | adapter 미사용 | fulfillment/claim 조합 |
| `originAreaInfo` | 상품에 따라 필요 | origin 원문 | 잘못된 shape | 코드 매핑+수입사 입력 |
| `sellerCodeInfo` | 선택/권장 | product_code | 미사용 | 올바른 위치에 매핑 |
| `optionInfo` | 옵션 상품 | standard_options | 일부 변환 오류 | 전용 변환기 수정 |
| `productAttributes` | 카테고리별 | mapped_attributes | runtime crash | list 계약 통일 |
| `taxType` | 정책/상품별 | 없음 | 누락 | account default+override |
| 인증 정보 | 카테고리별 | 없음 | 누락 | metadata 기반 입력/차단 |
| 미성년 구매 | 상품별 | 없음 | 누락 | account default+override |
| 상품정보제공고시 | 등록 필수 | 없음 | 누락 | 타입별 JSON 생성/편집 |
| 단위가격 | 카테고리별 | 없음 | 누락 | 해당 카테고리 차단 후 지원 |
| 채널 쇼핑 등록 | 필수 | listing_defaults 가능 | 검증 없음 | account setting schema |
| 채널 전시 상태 | 필수 | listing_defaults 가능 | 검증 없음 | 기본 `ON` |

## 13. 추가 컬럼과 저장 위치 결정

### 13.1 기본 원칙

기존 설계 문서 [`Marketplace Listing Service Design`](../superpowers/specs/2026-05-27-marketplace-listing-service-design.md)의 원칙을 유지한다.

- 공통 Product 테이블에 `smartstore_*` 컬럼을 대량 추가하지 않는다.
- marketplace-specific payload는 `market_listing_drafts.generated_payload` JSON에 둔다.
- 사용자 수정은 `override_patch` JSON에 둔다.
- 배송/반품/A/S/채널 플래그/기본 인증 정책은 account settings JSON에 둔다.
- 검색/목록에 필요한 요약값만 정규 컬럼으로 유지한다.

### 13.2 Product에 추가할 가치가 있는 공통 컬럼

즉시 후보:

| 컬럼 | 이유 |
| --- | --- |
| `stock_quantity` | 옵션 없는 상품의 판매 가능 수량. Smartstore와 Coupang 모두 공통 |

소스 데이터가 실제로 제공될 때만 후보:

| 컬럼 | 이유 |
| --- | --- |
| `manufacturer_name` | 고시와 검색 정보에 여러 마켓 공통 사용 가능 |
| `model_name` | 상품 고시/카탈로그/마켓 공통 재료 |
| `importer_name` | 수입상품 고시에 반복 사용되지만 공급사 데이터 존재 여부 확인 필요 |

값을 확보할 수 없는 컬럼을 먼저 추가하지 않는다.

### 13.3 Product에 추가하지 않을 필드

아래는 draft 또는 account JSON으로 처리한다.

- `statusType`, `saleType`
- `naverShoppingRegistration`
- `channelProductDisplayStatusType`
- 배송 방식, 택배사, 배송비
- 출고지/반품지 ID
- 반품비/교환비
- A/S 기본값
- 인증 기본/면제 정책
- `productInfoProvidedNotice` 전체 중첩 객체
- SEO/tag 설정
- Smartstore 이미지 업로드 URL

### 13.4 Account settings 권장 shape

현재 컬럼을 그대로 활용한다.

```json
{
  "connection_config": {
    "authType": "SELF"
  },
  "fulfillment_config": {
    "deliveryType": "DELIVERY",
    "deliveryAttributeType": "NORMAL",
    "deliveryCompany": "CJGLS",
    "shippingAddressId": 123,
    "deliveryFee": {
      "deliveryFeeType": "PAID",
      "baseFee": 3000,
      "deliveryFeePayType": "PREPAID"
    }
  },
  "claim_config": {
    "returnAddressId": 456,
    "returnDeliveryFee": 3000,
    "exchangeDeliveryFee": 6000
  },
  "listing_defaults": {
    "naverShoppingRegistration": false,
    "channelProductDisplayStatusType": "ON",
    "taxType": "TAX",
    "minorPurchasable": true,
    "afterServiceInfo": {
      "afterServiceTelephoneNumber": "...",
      "afterServiceGuideContent": "..."
    }
  },
  "generation_rules": {
    "pricingPolicy": {},
    "noticeDefaultPolicy": {},
    "certificationPolicy": {}
  }
}
```

이 shape는 제안이며 현재 Pydantic 모델로 검증되지 않는다. 구현 시 Smartstore 전용 settings schema를 만들어야 한다.

## 14. 권장 최소 외부 payload 예시

아래 예시는 구조를 설명하기 위한 일반 배송/옵션 없는 실물상품 예시다. 실제 카테고리에서는 고시와 인증 필드가 달라질 수 있으므로 그대로 복사해 전송하면 안 된다.

```json
{
  "originProduct": {
    "statusType": "SALE",
    "saleType": "NEW",
    "leafCategoryId": "50000000",
    "name": "등록 상품명",
    "detailContent": "<p>상품 상세</p>",
    "images": {
      "representativeImage": {
        "url": "https://shop-phinf.pstatic.net/naver-upload-result.jpg"
      }
    },
    "salePrice": 17200,
    "stockQuantity": 100,
    "deliveryInfo": {
      "deliveryType": "DELIVERY",
      "deliveryAttributeType": "NORMAL",
      "deliveryCompany": "검증된_택배사_코드",
      "deliveryFee": {
        "deliveryFeeType": "PAID",
        "baseFee": 3000,
        "deliveryFeePayType": "PREPAID"
      },
      "claimDeliveryInfo": {
        "returnDeliveryFee": 3000,
        "exchangeDeliveryFee": 6000,
        "shippingAddressId": 123,
        "returnAddressId": 456
      }
    },
    "detailAttribute": {
      "originAreaInfo": {
        "originAreaCode": "02",
        "importer": "수입사명",
        "plural": false
      },
      "sellerCodeInfo": {
        "sellerManagementCode": "ABC-001"
      },
      "afterServiceInfo": {
        "afterServiceTelephoneNumber": "0000-0000",
        "afterServiceGuideContent": "판매자 고객센터 문의"
      },
      "taxType": "TAX",
      "minorPurchasable": true,
      "productInfoProvidedNotice": {
        "productInfoProvidedNoticeType": "ETC",
        "etc": {
          "returnCostReason": "1",
          "noRefundReason": "1",
          "qualityAssuranceStandard": "1",
          "compensationProcedure": "1",
          "troubleShootingContents": "1",
          "itemName": "품명",
          "modelName": "모델명",
          "manufacturer": "제조사",
          "customerServicePhoneNumber": "0000-0000"
        }
      },
      "productAttributes": []
    }
  },
  "smartstoreChannelProduct": {
    "naverShoppingRegistration": false,
    "channelProductDisplayStatusType": "ON"
  }
}
```

구현 시 해야 할 정리:

- 내부 `pricing`은 이 외부 body에 포함하지 않음
- `null`, 빈 문자열, 불필요한 빈 객체 제거
- no-option 상품이면 `optionInfo` 생략
- 속성이 없으면 `productAttributes`도 필요 여부 확인 후 생략 가능
- 카테고리별 고시 타입과 인증 요구사항을 live metadata로 검증

## 15. 구현 권장 순서

### Phase 1. 계약과 validation 정리

1. Smartstore request builder를 외부 request body와 draft metadata로 분리
2. `mapped_attributes` 계약을 list로 통일
3. 원산지 mapper 작성
4. 옵션 mapper 수정
5. Smartstore account settings Pydantic schema 정의
6. 외부 payload 기준 validation 함수 추가
7. UI override 경로를 nested payload와 일치시킴

완료 조건:

- 네이버 최소 payload fixture에 대해 validation이 `valid`
- 현재 잘못된 payload fixture는 각각 명확한 error code로 차단

### Phase 2. 메타데이터와 이미지

1. category/attribute/origin/notice 조회 메서드 보완
2. 캐시 정책 정의
3. 이미지 다운로드 및 MIME/크기 검증
4. `/v1/product-images/upload` 호출
5. 업로드 결과 URL로 payload 치환

완료 조건:

- 동일 이미지 재시도 정책이 결정됨
- 최대 10개, 대표 1+추가 9 제한 검증
- 실패 시 attempt에 원인과 단계가 기록됨

### Phase 3. 실제 제출 worker

1. marketplace service에 Smartstore client 추가
2. account credential 복호화
3. access token 발급/캐시
4. queued submission attempt 실행 task 추가
5. 제출 직전 account settings 재조회 및 재검증
6. `POST /v2/products` 호출
7. 응답의 remote product ID 저장
8. job/draft/attempt 상태 전이 구현

권장 상태 전이:

```text
attempt: queued -> processing -> submitted | failed
draft: ready -> submitting -> submitted | failed
job: queued -> processing -> completed | partially_failed | failed
```

### Phase 4. 카테고리 확장

1. 대표 카테고리별 notice editor
2. 인증 대상 카테고리
3. 단위가격 대상 카테고리
4. 도서/식품/화학제품 등 특수 카테고리
5. N배송/오늘출발/렌탈/그룹상품

## 16. 테스트 계획

### 16.1 단위 테스트

- 원산지 원문 -> `originAreaInfo` 변환
- 수입산인데 importer가 없으면 차단
- 직접 입력 원산지인데 content가 없으면 차단
- no-option 상품에서 `optionInfo` 생략
- 1~3단계 조합형 옵션 변환
- 옵션 그룹 object shape 검증
- 옵션 SKU -> `sellerManagerCode`
- mapped attributes list 직접 소비
- `statusType=SALE` 기본값
- 채널 필수 플래그 기본값
- `productInfoProvidedNotice` 누락 차단
- 내부 `pricing` 외부 body 제거
- 빈/null 필드 정리

### 16.2 통합 테스트

- 실제 processor snapshot -> Smartstore adapter까지 이어지는 테스트
- 실제 list shape의 `mapped_attributes` 테스트
- account fulfillment/claim/listing defaults 조합 테스트
- UI override가 `originProduct.*`를 실제로 변경하는 테스트
- 제출 직전 재검증 테스트
- 이미지 업로드 성공/부분 실패/타임아웃 테스트
- OAuth 만료/갱신/동시 요청 테스트
- 네이버 400 `invalidInputs`와 `message` 저장 테스트
- 재시도 시 attempt number와 submitted payload 감사 기록 테스트

### 16.3 최소 실계정 검증

실 API 검증 전 준비:

- 판매자 동의
- 테스트 카테고리/상품 확정
- 배송/반품 주소 ID 확인
- 택배사 코드 확인
- 등록 직후 노출 여부 및 중지/삭제 절차 확인
- 실제 주문이 발생하지 않도록 가격/재고/전시 정책 확인

## 17. 아직 결정되지 않은 사항

다음 세션에서 코드 작성 전에 답해야 한다.

1. 첫 지원 상품 카테고리는 무엇인가?
2. 판매자별 `SELF` credential을 사용할 것인가, 솔루션 `SELLER` 흐름을 사용할 것인가?
3. 일반 배송 기본 택배사, 출고지, 반품지는 무엇인가?
4. 상품정보제공고시는 계정 기본값을 어느 범위까지 허용할 것인가?
5. 수입사/제조사/모델명 데이터는 공급사 파일에서 확보 가능한가?
6. 상품 기본 재고를 공급사에서 받을 수 있는가, 없으면 안전 기본값은 무엇인가?
7. 네이버쇼핑 등록 기본값은 false인가?
8. 새 상품은 즉시 `ON`으로 전시할 것인가, 검수용 `SUSPENSION` 정책이 필요한가?
9. 이미지 업로드 재사용을 위해 URL 매핑을 저장할 것인가, 매 제출 때 업로드할 것인가?
10. 등록 성공 후 `ProductPlatformMapping.platform_product_id`와 marketplace draft의 `remote_product_id`를 어떻게 동기화할 것인가?

## 18. 관련 repo 문서

- [Marketplace Listing Service Design](../superpowers/specs/2026-05-27-marketplace-listing-service-design.md)
- [Marketplace Review UI and Submission Foundation](../solutions/design-patterns/marketplace-review-ui-and-submission-foundation-2026-05-28.md)
- [Standard Product And Option Schema Design](../superpowers/specs/2026-06-01-standard-product-option-schema-design.md)
- [Multi-marketplace Attribute Extraction](../solutions/architecture-patterns/multi-marketplace-attribute-extraction-2026-05-29.md)

## 19. 문서 갱신 규칙

구현을 시작할 때 문서 상단의 API 버전과 날짜를 갱신한다. 다음 항목이 변경되면 이 문서도 함께 수정한다.

- 네이버 API 버전 또는 endpoint
- 상품 등록 request schema
- 지원 카테고리
- Smartstore account settings schema
- Product/snapshot 계약
- adapter version
- submission worker 상태 전이
- 운영상 기본 배송/고시/인증 정책
