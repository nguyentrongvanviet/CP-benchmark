#include <bits/stdc++.h>
using namespace std;
int main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n;cin>>n;vector<long long>cnt(100001),dp(100001);while(n--){int x;cin>>x;cnt[x]++;}dp[1]=cnt[1];for(int i=2;i<=100000;i++)dp[i]=max(dp[i-1],dp[i-2]+i*cnt[i]);cout<<dp[100000];return 0;}
