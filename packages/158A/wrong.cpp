#include <bits/stdc++.h>
using namespace std;
int main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n,k;cin>>n>>k;vector<int>a(n);for(int&x:a)cin>>x;int ans=0;for(int x:a)ans+=x>=a[k-1];cout<<ans;return 0;}
